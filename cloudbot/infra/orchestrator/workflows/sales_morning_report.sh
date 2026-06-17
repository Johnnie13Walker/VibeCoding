#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
SALES_RUNTIME_ENV_FILE="${SALES_RUNTIME_ENV_FILE:-}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
REPORT_NAME="sales_morning_report"

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
: "${SALES_TRIGGER:=scheduled}"
: "${SALES_JOB_NAME:=morning_sales_dispatch}"
: "${SALES_WORKFLOW_NAME:=infra/orchestrator/workflows/sales_morning_report.sh}"
: "${SALES_LOG_FILE:=}"

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/${REPORT_NAME}_${STAMP}.txt"

export SALES_TRIGGER
export SALES_JOB_NAME
export SALES_WORKFLOW_NAME
if [[ -n "$SALES_LOG_FILE" ]]; then
  export SALES_LOG_FILE
fi

log "sales_morning_report: старт (trigger=${SALES_TRIGGER}, job=${SALES_JOB_NAME})"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" -m agents.lev_petrovich --report sales --send
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "sales_morning_report: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "sales_morning_report: успешно, отчет=${REPORT_FILE}"
