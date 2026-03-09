#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "post_change_verify: запуск полного пост-измененческого набора проверок"
bash "$ROOT_DIR/checks/post_change_verify.sh"
log "post_change_verify: ОК"
