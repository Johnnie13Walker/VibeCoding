#!/usr/bin/env bash
# Деплой empty_companies_score на VPS как cron-job (2× в день, 09:30 и 18:30 МСК).
#
# Запуск на VPS:
#   sudo bash belberry/bitrix24/empty_companies_score/deploy/install.sh
#
# Что делает:
#   1) Использует существующий venv /opt/openclaw/venvs/crm_company_merge
#      (google-api-python-client уже стоит — общий для всех Belberry cron-задач).
#   2) Ставит сам пакет в этот venv через `pip install -e .` (editable, чтобы
#      `git pull` сразу подхватывался).
#   3) Проверяет наличие state.json и SA-ключа.
#   4) Кладёт две cron-записи под уникальными тегами:
#        утренний прогон 06:30 UTC = 09:30 МСК — с `--notify` (TG-сводка)
#        вечерний прогон 15:30 UTC = 18:30 МСК — без TG
#   5) Создаёт каталог /opt/openclaw/data/empty_co/ для JSON-дампов и state.
#
# Идемпотентно. При повторном запуске: если запись под тегом устарела — обновит.
#
# ВНИМАНИЕ про TZ: на этом VPS CRON_TZ=Europe/Moscow не действует (cron-демон
# исполняет в системном UTC). Расписание зашито в UTC явно (МСК - 3).

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/openclaw/repos/vibecoding}"
PKG_DIR="$REPO_ROOT/belberry/bitrix24/empty_companies_score"
PYTHON="/opt/openclaw/venvs/crm_company_merge/bin/python"
PIP="/opt/openclaw/venvs/crm_company_merge/bin/pip"
BITRIX_STATE_PATH="/opt/openclaw/state/bitrix_app/install.latest.json"
SA_KEY="${SA_KEY:-/opt/openclaw/secrets/finance-director-sheets.json}"
DATA_DIR="/opt/openclaw/data/empty_co"
LOG_FILE="/var/log/empty_companies_score.log"
WRAPPER_SRC="$PKG_DIR/deploy/wrapper.sh"
WRAPPER_DST="/usr/local/bin/cloudbot-empty-companies-score.sh"
LARISA_ENV="/etc/openclaw/larisa.env"
OPENCLAW_ENV="/opt/openclaw/.env"

# 06:30 UTC = 09:30 МСК (утро, c TG)
CRON_TAG_AM="# empty_companies_score (утренний прогон + TG) — Belberry"
CRON_LINE_AM="30 6 * * * $WRAPPER_DST --notify >> $LOG_FILE 2>&1"

# 15:30 UTC = 18:30 МСК (вечер, без TG)
CRON_TAG_PM="# empty_companies_score (вечерний прогон) — Belberry"
CRON_LINE_PM="30 15 * * * $WRAPPER_DST >> $LOG_FILE 2>&1"

echo "== checking prerequisites =="
test -d "$PKG_DIR"           || { echo "missing $PKG_DIR — git pull в $REPO_ROOT"; exit 1; }
test -x "$PYTHON"            || { echo "missing $PYTHON — venv не создан"; exit 1; }
test -x "$PIP"               || { echo "missing $PIP — venv сломан"; exit 1; }
test -f "$BITRIX_STATE_PATH" || { echo "missing $BITRIX_STATE_PATH"; exit 1; }
test -f "$SA_KEY"            || { echo "missing $SA_KEY"; exit 1; }
test -f "$WRAPPER_SRC"       || { echo "missing $WRAPPER_SRC"; exit 1; }
[ -f "$OPENCLAW_ENV" ] || echo "WARN: $OPENCLAW_ENV не найден — TELEGRAM_BOT_TOKEN не подхватится"
[ -f "$LARISA_ENV" ]   || echo "WARN: $LARISA_ENV не найден — LARISA_TELEGRAM_CHAT_ID не подхватится"

echo "== installing package (editable) =="
"$PIP" install --quiet -e "$PKG_DIR"

echo "== quick import smoke =="
"$PYTHON" -c "import empty_companies_score; from empty_companies_score import config, scorer, uploader, notifier, fetcher, bitrix_client; print('import OK; v=', empty_companies_score.__version__)"

echo "== installing wrapper =="
install -m 0755 "$WRAPPER_SRC" "$WRAPPER_DST"
echo "  $WRAPPER_DST"

echo "== ensuring data dir + log file =="
mkdir -p "$DATA_DIR"
touch "$LOG_FILE" && chown "$USER" "$LOG_FILE" || sudo touch "$LOG_FILE"

echo "== installing cron entries =="
TMPCRON=$(mktemp)
trap 'rm -f "$TMPCRON" "$TMPCRON.new"' EXIT
crontab -l 2>/dev/null > "$TMPCRON" || true

install_or_update() {
  local tag="$1" line="$2"
  if grep -Fq "$tag" "$TMPCRON"; then
    local existing
    existing=$(awk -v t="$tag" '$0==t{getline; print; exit}' "$TMPCRON")
    if [ "$existing" = "$line" ]; then
      echo "  '$tag' — already up to date"
    else
      echo "  '$tag' — updating"
      printf '    old: %s\n' "$existing"
      printf '    new: %s\n' "$line"
      awk -v t="$tag" -v new="$line" '
        { print }
        $0==t { getline; print new }
      ' "$TMPCRON" > "$TMPCRON.new" && mv "$TMPCRON.new" "$TMPCRON"
    fi
  else
    echo "  '$tag' — adding new"
    printf '\n%s\n%s\n' "$tag" "$line" >> "$TMPCRON"
  fi
}

install_or_update "$CRON_TAG_AM" "$CRON_LINE_AM"
install_or_update "$CRON_TAG_PM" "$CRON_LINE_PM"

crontab "$TMPCRON"
echo "✓ cron applied"

echo
echo "== current cron entries for empty_companies_score =="
crontab -l 2>/dev/null | grep -E "empty_companies_score" || echo "(none)"

echo
echo "Готово. Расписание (МСК): 09:30 утренний (с TG), 18:30 вечерний."
echo "Принудительный прогон:  BITRIX_STATE_PATH=$BITRIX_STATE_PATH GOOGLE_SERVICE_ACCOUNT_JSON=$SA_KEY EMPTY_CO_DATA_DIR=$DATA_DIR $PYTHON -m empty_companies_score [--notify] [--dry-run]"
echo "Лог:                    tail -f $LOG_FILE"
