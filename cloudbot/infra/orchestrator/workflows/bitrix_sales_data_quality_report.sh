#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
CATEGORY_ID="${BITRIX_SALES_DATA_QUALITY_CATEGORY_ID:-10}"
TARGET_SHEET_URL="${BITRIX_SALES_DATA_QUALITY_SHEET_URL:-https://docs.google.com/spreadsheets/d/1WMXNBqigq-uq7izvnkDfQsK3tgecHRc8nvvte1TXUKc/edit?gid=0#gid=0}"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
: "${PYTHON_BIN:=python3}"
: "${NODE_BIN:=node}"

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/bitrix_sales_data_quality_${STAMP}.json"
CSV_FILE="$REPORT_DIR/bitrix_sales_data_quality_${STAMP}.csv"
LOG_FILE="$REPORT_DIR/bitrix_sales_data_quality_${STAMP}.log"
UPLOAD_LOG_FILE="$REPORT_DIR/bitrix_sales_data_quality_upload_${STAMP}.json"

log "bitrix_sales_data_quality_report: старт category_id=${CATEGORY_ID}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_sales_data_quality_report.py" \
    --category-id "$CATEGORY_ID" \
    --csv "$CSV_FILE" \
    --json
) >"$REPORT_FILE" 2>"$LOG_FILE"
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_sales_data_quality_report: ошибка формирования отчета (rc=${rc}), лог=${LOG_FILE}"
  tail -n 120 "$LOG_FILE" || true
  exit "$rc"
fi

log "bitrix_sales_data_quality_report: отчет сформирован, json=${REPORT_FILE}, csv=${CSV_FILE}"

set +e
(
  cd "$ROOT_DIR"
  BITRIX_SALES_DATA_QUALITY_SHEET_URL="$TARGET_SHEET_URL" \
    "$NODE_BIN" "$ROOT_DIR/scripts/upload_bitrix_sales_data_quality_to_google_sheet.mjs" "$REPORT_FILE" "$TARGET_SHEET_URL"
) >"$UPLOAD_LOG_FILE" 2>&1
upload_rc=$?
set -e

if [[ "$upload_rc" -ne 0 ]]; then
  log "bitrix_sales_data_quality_report: ошибка выгрузки в Google Sheet (rc=${upload_rc}), лог=${UPLOAD_LOG_FILE}"
  tail -n 120 "$UPLOAD_LOG_FILE" || true
  exit "$upload_rc"
fi

log "bitrix_sales_data_quality_report: выгрузка в Google Sheet выполнена, лог=${UPLOAD_LOG_FILE}"
tail -n 80 "$UPLOAD_LOG_FILE" || true
