#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
DEAL_ID="${1:-${BITRIX_DEAL_ENRICHMENT_INSPECT_DEAL_ID:-}}"

if [[ -z "$DEAL_ID" ]]; then
  echo "Использование: $0 <deal_id>"
  exit 2
fi

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
REPORT_FILE="$REPORT_DIR/bitrix_deal_enrichment_inspect_${DEAL_ID}_${STAMP}.json"

log "bitrix_deal_enrichment_inspect: старт deal_id=${DEAL_ID}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_deal_enrichment_inspect.py" "$DEAL_ID" "${@:2}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_deal_enrichment_inspect: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_deal_enrichment_inspect: успешно, отчет=${REPORT_FILE}"
tail -n 120 "$REPORT_FILE" || true
