#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OUT_DIR="${OUT_DIR:-$REPORT_DIR/sessions}"
SESSION_NOTE="${1:-Автогенерация session handoff}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$OUT_DIR/session_handoff_${STAMP}.md"

latest_daily="$(ls -1t "$REPORT_DIR"/daily_ops_*_MSK.txt 2>/dev/null | head -n1 || true)"
latest_week="$(ls -1t "$REPORT_DIR"/weekly/weekly_focus_review_*_MSK.md 2>/dev/null | head -n1 || true)"
latest_friction="$(ls -1t "$REPORT_DIR"/friction/friction_scan_*_MSK.md 2>/dev/null | head -n1 || true)"

{
  echo "# Session Handoff (MSK)"
  echo
  echo "- Время: $(date '+%F %T %Z')"
  echo "- Примечание: ${SESSION_NOTE}"
  echo
  echo "## Ключевые артефакты"
  if [[ -n "$latest_daily" ]]; then
    echo "- daily_ops: $latest_daily"
  else
    echo "- daily_ops: отсутствует"
  fi
  if [[ -n "$latest_week" ]]; then
    echo "- weekly_focus_review: $latest_week"
  fi
  if [[ -n "$latest_friction" ]]; then
    echo "- friction_scan: $latest_friction"
  fi
  echo
  echo "## Изменения в рабочем дереве"
  if [[ -d "$ROOT_DIR/.git" ]] && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR" status --short || true
  else
    echo "- Локальный .git в текущем workspace не найден."
  fi
  echo
  echo "## Что сделать первым шагом в следующем запуске"
  echo "1. Запустить: DRY_RUN=1 make openclaw.post-change-verify"
  echo "2. Если ОК: DRY_RUN=0 make openclaw.daily-ops"
  echo "3. Проверить доставку статуса и наличие инцидента (если есть проблемы)."
} >"$OUT_FILE"

echo "$OUT_FILE"
