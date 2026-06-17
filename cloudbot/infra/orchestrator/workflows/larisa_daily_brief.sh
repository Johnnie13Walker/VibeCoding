#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
WHOOP_ENV_FILE="${WHOOP_ENV_FILE:-$ROOT_DIR/../whoop/.env}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

if [[ -f "$WHOOP_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$WHOOP_ENV_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
prepare_larisa_remote_todo_snapshot "$ROOT_DIR"
trap cleanup_larisa_remote_todo_snapshot EXIT

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/larisa_daily_brief_${STAMP}.txt"

args=(python3 -m agents.larisa_ivanovna --command get_day_brief)
if { [[ -n "${LARISA_TELEGRAM_CHAT_ID:-}" ]] || [[ -n "${TELEGRAM_CHAT_ID:-}" ]] || [[ -n "${TELEGRAM_TARGETS:-}" ]]; } && { [[ -n "${LARISA_TELEGRAM_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN:-}}" ]] || [[ "${LARISA_TELEGRAM_DRY_RUN:-0}" == "1" ]] || [[ "${TELEGRAM_DRY_RUN:-0}" == "1" ]]; }; then
  args+=(--send)
fi

log "larisa_daily_brief: старт"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "larisa_daily_brief: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "larisa_daily_brief: успешно, отчет=${REPORT_FILE}"
