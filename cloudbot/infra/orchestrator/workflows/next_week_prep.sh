#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/reports}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$REPORT_DIR" "$OUT_DIR"

log "next_week_prep: сбор плана на следующую неделю"
if ! prep_file="$(bash "$ROOT_DIR/scripts/next_week_prep.sh" "$REPORT_DIR" "$OUT_DIR")"; then
  log "next_week_prep: не удалось сформировать план, файл=${prep_file:-n/a}"
  exit 1
fi

log "next_week_prep: план сформирован ${prep_file}"
exit 0
