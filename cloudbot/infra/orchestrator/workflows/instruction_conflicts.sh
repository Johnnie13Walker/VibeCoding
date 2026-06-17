#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "instruction_conflicts: проверка конфликтов инструкций"
bash "$ROOT_DIR/checks/instruction_conflicts.sh"
log "instruction_conflicts: ОК"
