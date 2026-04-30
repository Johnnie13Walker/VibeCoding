#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
REPORT_TYPE="${1:-sales}"
EXTRA_ARGS=("${@:2}")

case "$REPORT_TYPE" in
  sales) REPORT_NAME="sales_brief" ;;
  followup) REPORT_NAME="sales_followup" ;;
  weekly) REPORT_NAME="sales_weekly_review" ;;
  pipeline) REPORT_NAME="sales_pipeline" ;;
  risks) REPORT_NAME="sales_risks" ;;
  focus) REPORT_NAME="sales_focus" ;;
  *) fail "Неизвестный тип sales-отчета: $REPORT_TYPE" ;;
esac

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
: "${PYTHON_BIN:=python3}"

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/${REPORT_NAME}_${STAMP}.txt"

args=("$PYTHON_BIN" "$ROOT_DIR/scripts/run_sales_copilot.py" --report "$REPORT_TYPE")
if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
  args+=("${EXTRA_ARGS[@]}")
fi
if [[ "${SALES_SEND:-1}" == "1" ]]; then
  args+=(--send)
fi

log "${REPORT_NAME}: старт"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "${REPORT_NAME}: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "${REPORT_NAME}: успешно, отчет=${REPORT_FILE}"
