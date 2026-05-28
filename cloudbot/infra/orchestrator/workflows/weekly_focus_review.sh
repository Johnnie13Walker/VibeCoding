#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "weekly_focus_review: обзор фокуса за 7 дней"
out_file="$(bash "$ROOT_DIR/scripts/weekly_focus_review.sh")"
log "weekly_focus_review: готово ${out_file}"
