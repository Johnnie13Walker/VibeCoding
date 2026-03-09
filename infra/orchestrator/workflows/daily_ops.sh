#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
INCIDENT_DIR="${INCIDENT_DIR:-$REPORT_DIR/incidents}"
SEND_TELEGRAM_STATUS="${SEND_TELEGRAM_STATUS:-auto}" # auto | always | never
STATUS_CHAT_ID="${STATUS_CHAT_ID:-${TELEGRAM_CHAT_ID:-}}"
FAIL_ON_PROBLEMS="${FAIL_ON_PROBLEMS:-0}"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$REPORT_DIR" "$INCIDENT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
DAILY_REPORT="$REPORT_DIR/daily_ops_${STAMP}.txt"
INTEGRATIONS_REPORT_DIR="$REPORT_DIR/daily_ops_integrations_${STAMP}"
mkdir -p "$INTEGRATIONS_REPORT_DIR"

has_problem=0
declare -a failed_steps=()
declare -a step_summaries=()

append_step_result() {
  local step_id="$1"
  local step_title="$2"
  local rc="$3"
  local log_file="$4"
  local status_word="ОК"

  if [[ "$rc" -ne 0 ]]; then
    status_word="ПРОБЛЕМА"
    has_problem=1
    failed_steps+=("$step_id")
  fi

  step_summaries+=("${step_id}=${status_word}")

  {
    echo "## ${step_title} (${step_id})"
    echo "Статус: ${status_word} (rc=${rc})"
    echo "Лог: ${log_file}"
    echo "Хвост лога:"
    echo '```'
    tail -n 80 "$log_file" || true
    echo '```'
    echo
  } >>"$DAILY_REPORT"
}

run_step() {
  local step_id="$1"
  local step_title="$2"
  shift 2

  local log_file="$REPORT_DIR/daily_ops_${STAMP}_${step_id}.log"
  log "daily_ops: ${step_title}"

  set +e
  "$@" >"$log_file" 2>&1
  local rc=$?
  set -e

  append_step_result "$step_id" "$step_title" "$rc" "$log_file"
}

send_telegram_status() {
  local text="$1"

  if [[ "$SEND_TELEGRAM_STATUS" == "never" ]]; then
    return 10
  fi

  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${STATUS_CHAT_ID:-}" ]]; then
    if [[ "$SEND_TELEGRAM_STATUS" == "always" ]]; then
      return 20
    fi
    return 21
  fi

  local api_base="${TELEGRAM_API_BASE_URL:-https://api.telegram.org}"
  local endpoint="${api_base%/}/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
  local body_file
  body_file="$(mktemp)"

  set +e
  local http_code
  http_code="$(curl -sS --max-time 15 -o "$body_file" -w '%{http_code}' \
    --data-urlencode "chat_id=${STATUS_CHAT_ID}" \
    --data-urlencode "text=${text}" \
    --data "disable_web_page_preview=true" \
    "$endpoint")"
  local curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 || "$http_code" != "200" ]]; then
    rm -f "$body_file"
    return 30
  fi

  if command -v jq >/dev/null 2>&1; then
    local ok_value
    ok_value="$(jq -r '.ok // false' "$body_file" 2>/dev/null || echo false)"
    rm -f "$body_file"
    [[ "$ok_value" == "true" ]] || return 31
  else
    if ! grep -q '"ok":[[:space:]]*true' "$body_file"; then
      rm -f "$body_file"
      return 32
    fi
    rm -f "$body_file"
  fi

  return 0
}

{
  echo "# Daily Ops Контроль"
  echo "Время: $(date '+%F %T %Z')"
  echo "Часовой пояс: Europe/Moscow"
  echo
  echo "## Параметры запуска"
  echo "- SEND_TELEGRAM_STATUS=${SEND_TELEGRAM_STATUS}"
  echo "- FAIL_ON_PROBLEMS=${FAIL_ON_PROBLEMS}"
  echo "- DRY_RUN=${DRY_RUN:-0}"
  echo
} >"$DAILY_REPORT"

run_step "vpn_verify" "Проверка VPN" bash "$ROOT_DIR/checks/vpn_verify.sh"
run_step "vpn_smoke" "Smoke Happ subscription" bash "$ROOT_DIR/checks/vpn_smoke_happ.sh"
run_step "morning_report" "Формирование утреннего VPN отчета" bash "$ROOT_DIR/checks/morning_health_report.sh"
run_step "whoop_morning_report" "Проверка свежести утреннего WHOOP отчета" \
  bash "$ROOT_DIR/infra/orchestrator/workflows/whoop_morning_report_check.sh"
run_step "context_contract" "Проверка актуальности контракта контекста" \
  bash "$ROOT_DIR/checks/context_contract_verify.sh"
run_step "instruction_conflicts" "Проверка конфликтов инструкций" \
  bash "$ROOT_DIR/checks/instruction_conflicts.sh"
run_step "integrations_verify" "Проверка интеграций и bot smoke" \
  env ENV_FILE="$ENV_INTEGRATIONS_FILE" bash "$ROOT_DIR/scripts/verify_integrations.sh" "$INTEGRATIONS_REPORT_DIR"

INTEGRATIONS_REPORT_FILE="$(ls -1t "$INTEGRATIONS_REPORT_DIR"/health_*_MSK.txt 2>/dev/null | head -n1 || true)"

overall_status="ОК"
if [[ "$has_problem" -ne 0 ]]; then
  overall_status="есть проблемы"
fi

status_text="Daily Ops $(date '+%F %T %Z'): ${overall_status}. Отчет: ${DAILY_REPORT}"
telegram_note="не отправлялось"

set +e
send_telegram_status "$status_text"
telegram_rc=$?
set -e

case "$telegram_rc" in
  0)
    telegram_note="доставлено"
    ;;
  10)
    telegram_note="отключено параметром SEND_TELEGRAM_STATUS=never"
    ;;
  20)
    telegram_note="ошибка: режим always, но TELEGRAM_BOT_TOKEN/STATUS_CHAT_ID не заданы"
    has_problem=1
    failed_steps+=("status_delivery")
    step_summaries+=("status_delivery=ПРОБЛЕМА")
    ;;
  21)
    telegram_note="пропуск: TELEGRAM_BOT_TOKEN/STATUS_CHAT_ID не заданы"
    has_problem=1
    failed_steps+=("status_delivery")
    step_summaries+=("status_delivery=ПРОБЛЕМА")
    ;;
  *)
    telegram_note="ошибка отправки в Telegram (rc=${telegram_rc})"
    has_problem=1
    failed_steps+=("status_delivery")
    step_summaries+=("status_delivery=ПРОБЛЕМА")
    ;;
esac

overall_status="ОК"
if [[ "$has_problem" -ne 0 ]]; then
  overall_status="есть проблемы"
fi

{
  echo "## Итог"
  echo "- Статус: ${overall_status}"
  echo "- Доставка статус-сообщения: ${telegram_note}"
  if [[ -n "$INTEGRATIONS_REPORT_FILE" ]]; then
    echo "- Отчет интеграций: ${INTEGRATIONS_REPORT_FILE}"
  fi
  if [[ "${#step_summaries[@]}" -gt 0 ]]; then
    echo "- Результаты шагов: ${step_summaries[*]}"
  fi
} >>"$DAILY_REPORT"

incident_file=""
if [[ "$has_problem" -ne 0 ]]; then
  incident_file="$INCIDENT_DIR/daily_ops_incident_${STAMP}.md"
  {
    echo "# Инцидент Daily Ops"
    echo
    echo "- Время: $(date '+%F %T %Z')"
    echo "- Статус: есть проблемы"
    echo "- Отчет: ${DAILY_REPORT}"
    echo "- Проблемные шаги: ${failed_steps[*]}"
    echo
    echo "## Что проверить в первую очередь"
    echo "1. Логи шагов daily_ops в каталоге reports."
    echo "2. Доступы и переменные окружения интеграций."
    echo "3. Доставку в Telegram и валидность токенов."
  } >"$incident_file"
fi

log "daily_ops: статус=${overall_status}"
log "daily_ops: отчет=${DAILY_REPORT}"
if [[ -n "$incident_file" ]]; then
  log "daily_ops: инцидент=${incident_file}"
fi

if [[ "$has_problem" -ne 0 && "$FAIL_ON_PROBLEMS" == "1" ]]; then
  exit 1
fi

exit 0
