#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

WHOOP_DIR="${WHOOP_DIR:-$ROOT_DIR/../whoop}"
WHOOP_HOST="${WHOOP_HOST:-${PRIMARY_HOST:-}}"
WHOOP_CHECK_MODE="${WHOOP_CHECK_MODE:-auto}"
WHOOP_REMOTE_ENV="${WHOOP_REMOTE_ENV:-/etc/openclaw/whoop.env}"
WHOOP_REMOTE_SCRIPT="${WHOOP_REMOTE_SCRIPT:-/usr/local/bin/send_whoop_report.py}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FAIL_ON_STALE="${FAIL_ON_STALE:-1}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$REPORT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
SUMMARY_FILE="$REPORT_DIR/whoop_morning_check_${STAMP}.txt"
DEFAULT_FILE="$REPORT_DIR/whoop_morning_check_${STAMP}_default.txt"
TODAY_FILE="$REPORT_DIR/whoop_morning_check_${STAMP}_today.txt"
EXPECTED_DATE="$(date '+%F')"

resolve_mode() {
  case "$WHOOP_CHECK_MODE" in
    local|remote)
      printf '%s\n' "$WHOOP_CHECK_MODE"
      ;;
    auto)
      if [[ -n "$WHOOP_HOST" ]]; then
        printf 'remote\n'
      else
        printf 'local\n'
      fi
      ;;
    *)
      fail "Неизвестный WHOOP_CHECK_MODE: $WHOOP_CHECK_MODE (доступно: auto, local, remote)"
      ;;
  esac
}

extract_report_date() {
  local file="$1"
  grep -oE '<b>WHOOP: отчёт за [0-9]{4}-[0-9]{2}-[0-9]{2}</b>' "$file" \
    | sed -E 's/.*за ([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/' \
    | head -n1
}

run_default_report() {
  (
    cd "$WHOOP_DIR"
    "$PYTHON_BIN" scripts/whoop_telegram_report.py send-report --dry-run --force
  ) >"$DEFAULT_FILE" 2>&1
}

run_today_report() {
  (
    cd "$WHOOP_DIR"
    LOOKBACK_DAYS=0 ACTIVITY_LOOKBACK_DAYS=0 \
      "$PYTHON_BIN" scripts/whoop_telegram_report.py send-report --dry-run --force
  ) >"$TODAY_FILE" 2>&1
}

run_remote_default_report() {
  local remote_script
  remote_script="$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow
env_file="$WHOOP_REMOTE_ENV"
script_file="$WHOOP_REMOTE_SCRIPT"
[ -f "\$env_file" ] || { echo "ОШИБКА: env не найден: \$env_file" >&2; exit 1; }
[ -f "\$script_file" ] || { echo "ОШИБКА: script не найден: \$script_file" >&2; exit 1; }
/usr/bin/env WHOOP_ENV_FILE="\$env_file" "\$script_file" send-report --dry-run --force
REMOTE
)"
  run_remote_script "$WHOOP_HOST" "$remote_script" >"$DEFAULT_FILE" 2>&1
}

run_remote_today_report() {
  local remote_script
  remote_script="$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow
env_file="$WHOOP_REMOTE_ENV"
script_file="$WHOOP_REMOTE_SCRIPT"
[ -f "\$env_file" ] || { echo "ОШИБКА: env не найден: \$env_file" >&2; exit 1; }
[ -f "\$script_file" ] || { echo "ОШИБКА: script не найден: \$script_file" >&2; exit 1; }
/usr/bin/env WHOOP_ENV_FILE="\$env_file" LOOKBACK_DAYS=0 ACTIVITY_LOOKBACK_DAYS=0 "\$script_file" send-report --dry-run --force
REMOTE
)"
  run_remote_script "$WHOOP_HOST" "$remote_script" >"$TODAY_FILE" 2>&1
}

ensure_dry_run_report() {
  local file="$1"
  local label="$2"

  if [[ "${DRY_RUN:-0}" != "1" || -f "$file" ]]; then
    return 0
  fi

  {
    printf '<b>WHOOP: отчёт за %s</b>\n' "$EXPECTED_DATE"
    printf 'Режим: dry-run (%s)\n' "$label"
  } >"$file"
}

CHECK_MODE_RESOLVED="$(resolve_mode)"

if [[ "$CHECK_MODE_RESOLVED" == "local" ]]; then
  [[ -d "$WHOOP_DIR" ]] || fail "Каталог WHOOP не найден: $WHOOP_DIR"
else
  require_env WHOOP_HOST SSH_USER SSH_KEY_PATH SSH_PORT
fi

log "WHOOP morning report check: запуск dry-run с текущей конфигурацией"
if [[ "$CHECK_MODE_RESOLVED" == "remote" ]]; then
  run_cmd "run_remote_default_report"
else
  run_cmd "run_default_report"
fi
log "WHOOP morning report check: запуск dry-run с режимом 'сегодня'"
if [[ "$CHECK_MODE_RESOLVED" == "remote" ]]; then
  run_cmd "run_remote_today_report"
else
  run_cmd "run_today_report"
fi

ensure_dry_run_report "$DEFAULT_FILE" "default"
ensure_dry_run_report "$TODAY_FILE" "today"

default_date="$(extract_report_date "$DEFAULT_FILE" || true)"
today_date="$(extract_report_date "$TODAY_FILE" || true)"

status="ОК"
if [[ "$default_date" != "$EXPECTED_DATE" ]]; then
  status="ПРОБЛЕМА"
fi

{
  echo "# WHOOP Morning Report Check"
  echo "Время: $(date '+%F %T %Z')"
  echo "Часовой пояс: Europe/Moscow"
  echo "Источник проверки: ${CHECK_MODE_RESOLVED}"
  if [[ "$CHECK_MODE_RESOLVED" == "remote" ]]; then
    echo "Хост: ${WHOOP_HOST}"
    echo "Remote env: ${WHOOP_REMOTE_ENV}"
    echo "Remote script: ${WHOOP_REMOTE_SCRIPT}"
  else
    echo "Локальный каталог WHOOP: ${WHOOP_DIR}"
  fi
  echo "Ожидаемая дата отчёта: $EXPECTED_DATE"
  echo "Дата отчёта по умолчанию: ${default_date:-не определена}"
  echo "Дата отчёта в режиме 'сегодня': ${today_date:-не определена}"
  echo "Статус: $status"
  echo
  echo "Файлы:"
  echo "- default: $DEFAULT_FILE"
  echo "- today: $TODAY_FILE"
} >"$SUMMARY_FILE"

log "WHOOP morning report check: отчет=${SUMMARY_FILE}"

if [[ "$status" != "ОК" && "$FAIL_ON_STALE" == "1" ]]; then
  fail "WHOOP утренний отчет по умолчанию не соответствует текущей дате ($EXPECTED_DATE)"
fi

exit 0
