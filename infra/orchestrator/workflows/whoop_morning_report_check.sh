#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

WHOOP_DIR="${WHOOP_DIR:-/Users/pro2kuror/Documents/WHOOP}"
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

if [[ ! -d "$WHOOP_DIR" ]]; then
  fail "Каталог WHOOP не найден: $WHOOP_DIR"
fi

log "WHOOP morning report check: запуск dry-run с текущей конфигурацией"
run_cmd "run_default_report"
log "WHOOP morning report check: запуск dry-run с режимом 'сегодня'"
run_cmd "run_today_report"

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
