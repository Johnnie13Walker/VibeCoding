#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "friction_scan: анализ повторяющихся точек трения"
out_file="$(bash "$ROOT_DIR/scripts/friction_scan.sh")"
log "friction_scan: готово ${out_file}"
