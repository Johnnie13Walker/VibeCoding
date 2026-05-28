#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
REPORT_TYPE="weekly"
REPORT_NAME="sales_weekly_review"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/${REPORT_NAME}_${STAMP}.txt"

args=(python3 -m agents.lev_petrovich --report "$REPORT_TYPE")
stop_reason=""
weekly_chat_id="${SALES_WEEKLY_TELEGRAM_CHAT_ID:-${SALES_TELEGRAM_CHAT_ID:-${TELEGRAM_CHAT_ID:-}}}"
if [[ -z "$weekly_chat_id" ]]; then
  stop_reason="STOP-POINT: не задан sales chat_id, fixed target для weekly-отчёта не настроен."
elif [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || [[ "${TELEGRAM_DRY_RUN:-0}" == "1" ]] || [[ "${SALES_TELEGRAM_DRY_RUN:-0}" == "1" ]]; then
  args+=(--send --chat-id "$weekly_chat_id")
else
  stop_reason="STOP-POINT: sales chat_id задан, но TELEGRAM_BOT_TOKEN не настроен и dry-run не включён."
fi

log "sales_weekly_review: старт"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "sales_weekly_review: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

if [[ -n "$stop_reason" ]]; then
  printf '\n%s\n' "$stop_reason" >>"$REPORT_FILE"
  log "sales_weekly_review: ${stop_reason} отчет=${REPORT_FILE}"
else
  log "sales_weekly_review: успешно, отчет=${REPORT_FILE}"
fi
