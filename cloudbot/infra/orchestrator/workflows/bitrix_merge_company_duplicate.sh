#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
TARGET_COMPANY_ID="${1:-${BITRIX_MERGE_TARGET_COMPANY_ID:-}}"
SOURCE_COMPANY_ID="${2:-${BITRIX_MERGE_SOURCE_COMPANY_ID:-}}"

if [[ -z "$TARGET_COMPANY_ID" || -z "$SOURCE_COMPANY_ID" ]]; then
  echo "Использование: $0 <target_company_id> <source_company_id> [--deal-id <deal_id>] [--apply]"
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
MODE="dry_run"
for arg in "$@"; do
  if [[ "$arg" == "--apply" ]]; then
    MODE="apply"
  fi
done
REPORT_FILE="$REPORT_DIR/bitrix_merge_company_duplicate_${TARGET_COMPANY_ID}_${SOURCE_COMPANY_ID}_${MODE}_${STAMP}.json"

log "bitrix_merge_company_duplicate: старт target=${TARGET_COMPANY_ID}, source=${SOURCE_COMPANY_ID}, mode=${MODE}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_merge_company_duplicate.py" \
    --target-company-id "$TARGET_COMPANY_ID" \
    --source-company-id "$SOURCE_COMPANY_ID" \
    "${@:3}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_merge_company_duplicate: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 180 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_merge_company_duplicate: успешно, отчет=${REPORT_FILE}"
tail -n 180 "$REPORT_FILE" || true
