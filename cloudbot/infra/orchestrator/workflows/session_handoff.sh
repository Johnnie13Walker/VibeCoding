#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

NOTE="${1:-Автоматический handoff после сессии}"

log "session_handoff: формирование session артефактов"
out_file="$(bash "$ROOT_DIR/scripts/session_artifacts.sh" "$NOTE")"
log "session_handoff: готово ${out_file}"
