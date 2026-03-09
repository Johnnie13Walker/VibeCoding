#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
mkdir -p "$REPORT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$REPORT_DIR/ops_intelligence_${STAMP}.md"

log "ops_intelligence: запуск связки workflow (контекст/трения/фокус/24h/handoff)"

context_file="$(bash "$ROOT_DIR/scripts/context_snapshot.sh")"
friction_file="$(bash "$ROOT_DIR/scripts/friction_scan.sh")"
weekly_file="$(bash "$ROOT_DIR/scripts/weekly_focus_review.sh")"
high_file="$(bash "$ROOT_DIR/scripts/high_leverage_24h.sh")"
handoff_file="$(bash "$ROOT_DIR/scripts/session_artifacts.sh" "ops_intelligence bundle")"

{
  echo "# Ops Intelligence Bundle (MSK)"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  echo
  echo "## Артефакты"
  echo "- context_snapshot: ${context_file}"
  echo "- friction_scan: ${friction_file}"
  echo "- weekly_focus_review: ${weekly_file}"
  echo "- high_leverage_24h: ${high_file}"
  echo "- session_handoff: ${handoff_file}"
} >"$OUT_FILE"

log "ops_intelligence: готово ${OUT_FILE}"
