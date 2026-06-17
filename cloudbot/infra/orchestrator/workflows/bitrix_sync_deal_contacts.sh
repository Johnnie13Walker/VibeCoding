#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
DEAL_ID="${BITRIX_SYNC_DEAL_CONTACTS_DEAL_ID:-${1:-}}"
APPLY="${BITRIX_SYNC_DEAL_CONTACTS_APPLY:-0}"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
: "${PYTHON_BIN:=python3}"

if [[ -z "$DEAL_ID" ]]; then
  fail "Не задана сделка: укажи BITRIX_SYNC_DEAL_CONTACTS_DEAL_ID или первый аргумент workflow."
fi

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/bitrix_sync_deal_contacts_${DEAL_ID}_${STAMP}.json"

args=("$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_sync_deal_company_contacts.py" --deal-id "$DEAL_ID" --json)
if [[ "$APPLY" == "1" ]]; then
  args+=(--apply)
fi

log "bitrix_sync_deal_contacts: старт deal_id=${DEAL_ID}, apply=${APPLY}"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_sync_deal_contacts: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_sync_deal_contacts: успешно, отчет=${REPORT_FILE}"
tail -n 120 "$REPORT_FILE" || true
