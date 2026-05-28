#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
DEAL_ID="${1:-${BITRIX_LINK_DEAL_COMPANY_DEAL_ID:-}}"
COMPANY_ID="${2:-${BITRIX_LINK_DEAL_COMPANY_COMPANY_ID:-}}"

if [[ -z "$DEAL_ID" || -z "$COMPANY_ID" ]]; then
  echo "Использование: $0 <deal_id> <company_id> [--apply]"
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
REPORT_FILE="$REPORT_DIR/bitrix_link_deal_existing_company_${DEAL_ID}_${COMPANY_ID}_${MODE}_${STAMP}.json"

log "bitrix_link_deal_existing_company: старт deal_id=${DEAL_ID}, company_id=${COMPANY_ID}, mode=${MODE}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_link_deal_existing_company.py" \
    --deal-id "$DEAL_ID" \
    --company-id "$COMPANY_ID" \
    "${@:3}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_link_deal_existing_company: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 160 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_link_deal_existing_company: успешно, отчет=${REPORT_FILE}"
tail -n 160 "$REPORT_FILE" || true
