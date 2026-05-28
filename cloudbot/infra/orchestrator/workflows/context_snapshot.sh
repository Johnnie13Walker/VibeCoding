#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "context_snapshot: формирование слепка контекста"
out_file="$(bash "$ROOT_DIR/scripts/context_snapshot.sh")"
log "context_snapshot: готово ${out_file}"
