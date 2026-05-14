#!/usr/bin/env bash
# Деплой dup_sheet_sync.py на VPS как cron-job.
#
# Запуск на VPS (а не на мак-ноуте):
#   sudo bash belberry/bitrix24/deploy/install_dup_sheet_sync.sh
#
# Что делает:
#   1) Использует существующее venv /opt/openclaw/venvs/crm_company_merge
#      (там уже стоит google-api-python-client — общий для всех cron-задач Belberry).
#   2) Проверяет что service-account JSON для Google Sheets лежит на месте.
#   3) Прогоняет dry-run-ish smoke (читает текущее состояние листа без write).
#   4) Кладёт cron-запись 09:30 и 18:30 МСК в crontab пользователя.
#
# Идемпотентно: повторный запуск ничего не ломает.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/openclaw/repos/vibecoding}"
SCRIPT="$REPO_ROOT/belberry/bitrix24/dup_sheet_sync.py"
PYTHON="/opt/openclaw/venvs/crm_company_merge/bin/python"
BITRIX_STATE_PATH="/opt/openclaw/state/bitrix_app/install.latest.json"
SA_KEY="${SA_KEY:-/opt/openclaw/secrets/finance-director-sheets.json}"
LOG_FILE="/var/log/dup_sheet_sync.log"
CRON_TAG="# dup_sheet_sync — витрина дублей компаний Belberry"
CRON_LINE="30 9,18 * * * BITRIX_STATE_PATH=$BITRIX_STATE_PATH GOOGLE_SERVICE_ACCOUNT_JSON=$SA_KEY $PYTHON $SCRIPT >> $LOG_FILE 2>&1"

echo "== checking prerequisites =="
test -f "$SCRIPT"            || { echo "missing $SCRIPT — git pull в $REPO_ROOT"; exit 1; }
test -x "$PYTHON"            || { echo "missing $PYTHON — venv не создан"; exit 1; }
test -f "$BITRIX_STATE_PATH" || { echo "missing $BITRIX_STATE_PATH"; exit 1; }
test -f "$SA_KEY"            || { echo "missing $SA_KEY — положить ключ service-account"; exit 1; }

echo "== quick import smoke =="
BITRIX_STATE_PATH="$BITRIX_STATE_PATH" \
GOOGLE_SERVICE_ACCOUNT_JSON="$SA_KEY" \
"$PYTHON" -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('dss', '$SCRIPT')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
svc = m.sheets_service()
print('sheets OK; tabs:', [s['properties']['title'] for s in svc.spreadsheets().get(spreadsheetId=m.SHEET_ID).execute()['sheets']])
"

echo "== ensuring log file exists =="
touch "$LOG_FILE" && chown "$USER" "$LOG_FILE" || sudo touch "$LOG_FILE"

echo "== installing cron entry =="
TMPCRON=$(mktemp)
trap 'rm -f "$TMPCRON"' EXIT
crontab -l 2>/dev/null > "$TMPCRON" || true
if grep -Fq "$CRON_TAG" "$TMPCRON"; then
  echo "cron entry already installed, leaving alone"
else
  printf '\n%s\n%s\n' "$CRON_TAG" "$CRON_LINE" >> "$TMPCRON"
  crontab "$TMPCRON"
  echo "✓ cron installed:"
  printf '   %s\n' "$CRON_LINE"
fi

echo
echo "== current cron entries containing 'dup_' =="
crontab -l 2>/dev/null | grep -E "dup_|$CRON_TAG" || echo "(none)"

echo
echo "Готово. Первый запуск произойдёт по cron в 09:30 или 18:30 МСК."
echo "Принудительный прогон: $PYTHON $SCRIPT"
echo "Лог:                   tail -f $LOG_FILE"
