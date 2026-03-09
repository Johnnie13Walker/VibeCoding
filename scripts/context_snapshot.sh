#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
CONTRACT_FILE="${CONTRACT_FILE:-$ROOT_DIR/ops/owner_operating_contract_MSK.md}"
OUT_DIR="${OUT_DIR:-$REPORT_DIR/context}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$OUT_DIR/context_snapshot_${STAMP}.md"

latest_daily="$(ls -1t "$REPORT_DIR"/daily_ops_*_MSK.txt 2>/dev/null | head -n1 || true)"
latest_week="$(ls -1t "$REPORT_DIR"/next_week_prep_*_MSK.md 2>/dev/null | head -n1 || true)"
latest_incident="$(ls -1t "$REPORT_DIR"/incidents/daily_ops_incident_*_MSK.md 2>/dev/null | head -n1 || true)"

incident_count_7d="$(find "$REPORT_DIR"/incidents -type f -name 'daily_ops_incident_*_MSK.md' -mtime -7 2>/dev/null | wc -l | tr -d ' ')"
daily_count_7d="$(find "$REPORT_DIR" -maxdepth 1 -type f -name 'daily_ops_*_MSK.txt' -mtime -7 2>/dev/null | wc -l | tr -d ' ')"

{
  echo "# Context Snapshot (MSK)"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  echo "- Daily отчеты за 7 дней: ${daily_count_7d}"
  echo "- Инциденты за 7 дней: ${incident_count_7d}"
  echo
  echo "## Ключевые опоры контекста"
  echo "1. Часовой пояс: Europe/Moscow."
  echo "2. Язык: русский."
  echo "3. Режим работы: через orchestrator workflow."
  echo "4. Базовый контур: daily_ops + next_week_prep + post_change_verify."
  echo
  echo "## Источники для следующей сессии"
  if [[ -n "$latest_daily" ]]; then
    echo "- Последний daily_ops: $latest_daily"
  else
    echo "- Последний daily_ops: отсутствует"
  fi
  if [[ -n "$latest_week" ]]; then
    echo "- Последний next_week_prep: $latest_week"
  else
    echo "- Последний next_week_prep: отсутствует"
  fi
  if [[ -n "$latest_incident" ]]; then
    echo "- Последний инцидент: $latest_incident"
  else
    echo "- Последний инцидент: отсутствует"
  fi
  echo
  echo "## Приоритеты владельца (из контракта)"
  if [[ -f "$CONTRACT_FILE" ]]; then
    sed -n '/^## Приоритеты/,/^## /p' "$CONTRACT_FILE" | sed '$d'
  else
    echo "- Контракт не найден: $CONTRACT_FILE"
  fi
  echo
  echo "## Что хранить в долгой памяти"
  echo "- SLA ежедневного статуса (09:30 МСК)."
  echo "- Обязательные интеграции и критерии их готовности."
  echo "- Повторяющиеся причины инцидентов и принятые guardrail-решения."
  echo
  echo "## Что не хранить в долгой памяти"
  echo "- Шумные хвосты логов и промежуточные DRY_RUN выводы."
  echo "- Одноразовые диагностические команды без устойчивой ценности."
} >"$OUT_FILE"

echo "$OUT_FILE"
