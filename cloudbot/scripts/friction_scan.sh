#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OUT_DIR="${OUT_DIR:-$REPORT_DIR/friction}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$OUT_DIR/friction_scan_${STAMP}.md"

tmp_all="$(mktemp)"
trap 'rm -f "$tmp_all"' EXIT

find "$REPORT_DIR" -maxdepth 1 -type f -name 'daily_ops_*_MSK.txt' -mtime -14 -print0 2>/dev/null \
  | xargs -0 cat 2>/dev/null \
  | grep -E '\[ПРОБЛЕМА\]|ПРОБЛЕМА' \
  | sed 's/^[[:space:]]*//' >"$tmp_all" || true

{
  echo "# Friction Scan (MSK)"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  echo "- Период: последние 14 дней"
  echo
  echo "## Повторяющиеся точки трения"
  if [[ -s "$tmp_all" ]]; then
    awk '{count[$0]++} END {for (line in count) printf "%d\t%s\n", count[line], line}' "$tmp_all" \
      | sort -rn \
      | head -n 12 \
      | while IFS=$'\t' read -r cnt line; do
          echo "- x${cnt}: ${line}"
        done
  else
    echo "- Повторяющиеся проблемы не обнаружены."
  fi
  echo
  echo "## Приоритет автоматизации (сначала)"
  echo "1. Проверка доступов/токенов до старта critical workflow."
  echo "2. Авто-детект недоставки статуса в Telegram."
  echo "3. Жесткий fail-fast на конфликте расписаний и SLA."
  echo "4. Единый session handoff после каждой сессии."
} >"$OUT_FILE"

echo "$OUT_FILE"
