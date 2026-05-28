#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OUT_DIR="${OUT_DIR:-$REPORT_DIR/weekly}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$OUT_DIR/weekly_focus_review_${STAMP}.md"

daily_total="$(find "$REPORT_DIR" -maxdepth 1 -type f -name 'daily_ops_*_MSK.txt' -mtime -7 2>/dev/null | wc -l | tr -d ' ')"
incident_total="$(find "$REPORT_DIR"/incidents -type f -name 'daily_ops_incident_*_MSK.md' -mtime -7 2>/dev/null | wc -l | tr -d ' ')"
score=10
if (( daily_total == 0 )); then
  score=$((score - 4))
fi
if (( incident_total > 0 )); then
  score=$((score - 2))
fi
if [[ ! -f "$ROOT_DIR/ops/owner_operating_contract_MSK.md" ]]; then
  score=$((score - 2))
fi
if [[ ! -f "$ROOT_DIR/ops/assumption_registry_MSK.md" ]]; then
  score=$((score - 1))
fi
if (( score < 1 )); then
  score=1
fi

git_log_file="$(mktemp)"
trap 'rm -f "$git_log_file"' EXIT

if [[ -d "$ROOT_DIR/.git" ]] && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT_DIR" log --since='7 days ago' --pretty='%ad | %h | %s' --date=format-local:'%Y-%m-%d %H:%M:%S %Z' >"$git_log_file" 2>/dev/null || true
fi

{
  echo "# Weekly Focus Review (MSK)"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  echo "- Daily_ops запусков за 7 дней: ${daily_total}"
  echo "- Инцидентов за 7 дней: ${incident_total}"
  echo
  echo "## Что реально двигало к цели"
  echo "1. Запуски orchestrator workflow с формированием проверяемых отчетов."
  echo "2. Внедрение guardrail-проверок (контракт контекста, конфликты инструкций)."
  echo "3. Переход на единый контур daily_ops + next_week_prep."
  echo
  echo "## Что похоже на суету"
  echo "1. Повторные прогоны без закрытия первопричин проблем доступа/токенов."
  echo "2. Локальные проверки без фиксации артефактов handoff."
  echo
  echo "## Оценка точности модели приоритетов (1-10)"
  echo "1. Текущая оценка: ${score}/10."
  echo "2. Что тянет вниз: инциденты за неделю и неполная готовность интеграций."
  echo "3. Как повысить: закрыть токены/доставку и держать daily_ops в fail-fast режиме."
  echo
  echo "## Динамика приоритетов"
  echo "1. Ранее: разовые проверки и настройка окружения."
  echo "2. Сейчас: стабильная эксплуатация и контроль доставки."
  echo "3. Следующий этап: автоматический контроль качества после каждого изменения."
  echo
  echo "## Изменения за 7 дней (git)"
  if [[ -s "$git_log_file" ]]; then
    sed -n '1,40p' "$git_log_file"
  else
    echo "- Git-история недоступна или пуста за период."
  fi
} >"$OUT_FILE"

echo "$OUT_FILE"
