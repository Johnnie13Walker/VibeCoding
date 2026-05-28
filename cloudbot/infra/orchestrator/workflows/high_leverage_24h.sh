#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "high_leverage_24h: подбор шага максимального эффекта"
out_file="$(bash "$ROOT_DIR/scripts/high_leverage_24h.sh")"
log "high_leverage_24h: готово ${out_file}"
