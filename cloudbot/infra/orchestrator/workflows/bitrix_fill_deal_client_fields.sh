#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
DEAL_ID="${1:-${BITRIX_FILL_DEAL_CLIENT_FIELDS_DEAL_ID:-}}"

if [[ -z "$DEAL_ID" ]]; then
  echo "Использование: $0 <deal_id> [--apply]"
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
REPORT_FILE="$REPORT_DIR/bitrix_fill_deal_client_fields_${DEAL_ID}_${MODE}_${STAMP}.json"

log "bitrix_fill_deal_client_fields: старт deal_id=${DEAL_ID}, mode=${MODE}"

set +e
(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_fill_deal_client_fields.py" --deal-id "$DEAL_ID" "${@:2}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_fill_deal_client_fields: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 160 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_fill_deal_client_fields: успешно, отчет=${REPORT_FILE}"
tail -n 160 "$REPORT_FILE" || true
