#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
INPUT_JSON="${BITRIX_DEAL_DUPLICATE_INPUT_JSON:-}"
LIMIT="${BITRIX_DEAL_DUPLICATE_LIMIT:-1000}"
ALL="${BITRIX_DEAL_DUPLICATE_ALL:-0}"
REMOTE_BRIDGE="${BITRIX_DEAL_DUPLICATE_REMOTE_BRIDGE:-1}"

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
REPORT_FILE="$REPORT_DIR/bitrix_deal_duplicate_plan_${STAMP}.txt"

args=("$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_deal_duplicate_plan.py")
if [[ "$ALL" == "1" ]]; then
  args+=("--all")
else
  args+=("--limit" "$LIMIT")
fi
if [[ -n "$INPUT_JSON" ]]; then
  args+=("--input-json" "$INPUT_JSON")
elif [[ "$REMOTE_BRIDGE" == "1" ]]; then
  args+=("--remote-bridge")
fi
if [[ "${BITRIX_DEAL_DUPLICATE_SKIP_PRODUCTS:-0}" == "1" ]]; then
  args+=("--skip-product-rows")
fi

log "bitrix_deal_duplicate_plan: старт dry-run"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_deal_duplicate_plan: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_deal_duplicate_plan: успешно, отчет=${REPORT_FILE}"
tail -n 80 "$REPORT_FILE" || true
