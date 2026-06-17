#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
SALES_RUNTIME_ENV_FILE="${SALES_RUNTIME_ENV_FILE:-}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
REPORT_NAME="sales_morning_report_check"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

if [[ -n "$SALES_RUNTIME_ENV_FILE" && -f "$SALES_RUNTIME_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SALES_RUNTIME_ENV_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
: "${PYTHON_BIN:=python3}"
: "${SALES_JOB_NAME:=morning_sales_dispatch}"
: "${SALES_MORNING_ALERT:=1}"
: "${SALES_LOG_FILE:=}"

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/${REPORT_NAME}_${STAMP}.txt"

export SALES_JOB_NAME
export SALES_MORNING_ALERT
if [[ -n "$SALES_LOG_FILE" ]]; then
  export SALES_LOG_FILE
fi

log "sales_morning_report_check: старт (job=${SALES_JOB_NAME})"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" -m cloudbot.devops.sales_dispatch_health --send-alert
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "sales_morning_report_check: alert/ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "sales_morning_report_check: успешно, отчет=${REPORT_FILE}"
