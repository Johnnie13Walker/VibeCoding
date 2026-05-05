#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
MODE="${BITRIX_BIZPROC_SYNC_CONTACTS_MODE:-${1:-register-activity}}"
APPLY="${BITRIX_BIZPROC_SYNC_CONTACTS_APPLY:-0}"

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
REPORT_FILE="$REPORT_DIR/bitrix_bizproc_sync_contacts_${MODE}_${STAMP}.json"

args=("$PYTHON_BIN" "$ROOT_DIR/scripts/bitrix_bizproc_sync_deal_contacts_activity.py" "$MODE" --json)
if [[ "$APPLY" == "1" ]]; then
  args+=(--apply)
fi

log "bitrix_bizproc_sync_contacts: старт mode=${MODE}, apply=${APPLY}"

set +e
(
  cd "$ROOT_DIR"
  "${args[@]}"
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_bizproc_sync_contacts: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "bitrix_bizproc_sync_contacts: успешно, отчет=${REPORT_FILE}"
tail -n 120 "$REPORT_FILE" || true
