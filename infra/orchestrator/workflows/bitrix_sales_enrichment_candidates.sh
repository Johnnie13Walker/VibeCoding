#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
CATEGORY_ID="${BITRIX_SALES_ENRICHMENT_CATEGORY_ID:-10}"

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
REPORT_FILE="$REPORT_DIR/bitrix_sales_enrichment_candidates_${STAMP}.json"
CSV_FILE="$REPORT_DIR/bitrix_sales_enrichment_candidates_${STAMP}.csv"

log "bitrix_sales_enrichment_candidates: старт category_id=${CATEGORY_ID}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_sales_enrichment_candidates.py" \
    --category-id "$CATEGORY_ID" \
    --csv "$CSV_FILE" \
    --json
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_sales_enrichment_candidates: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_sales_enrichment_candidates: успешно, отчет=${REPORT_FILE}, csv=${CSV_FILE}"
tail -n 120 "$REPORT_FILE" || true
