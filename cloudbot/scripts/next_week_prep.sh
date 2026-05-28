#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${1:-$ROOT_DIR/reports}"
OUT_DIR="${2:-$ROOT_DIR/reports}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

latest_daily="$(ls -1t "$REPORT_DIR"/daily_ops_*_MSK.txt 2>/dev/null | head -n1 || true)"
stamp="$(date '+%Y%m%d_%H%M%S_MSK')"
out_file="$OUT_DIR/next_week_prep_${stamp}.md"

if [[ -z "$latest_daily" ]]; then
  {
    echo "# План подготовки на следующую неделю"
    echo
    echo "Время: $(date '+%F %T %Z')"
    echo
    echo "## Статус"
    echo "- Нет базового daily_ops отчета. Сначала запустить:"
    echo "  - DRY_RUN=0 make openclaw.daily-ops"
  } >"$out_file"
  echo "$out_file"
  exit 1
fi

daily_problems=()
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  daily_problems+=("$line")
done < <(grep -E "ПРОБЛЕМА|\[ПРОБЛЕМА\]" "$latest_daily" | sed 's/^[[:space:]]*//' | head -n 40 || true)
integration_report="$(sed -n 's/^- Отчет интеграций: //p' "$latest_daily" | head -n1)"

integration_problems=()
if [[ -n "$integration_report" && -f "$integration_report" ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    integration_problems+=("$line")
  done < <(grep -E "^\[ПРОБЛЕМА\]" "$integration_report" | sed 's/^\[ПРОБЛЕМА\][[:space:]]*//')
fi

{
  echo "# План подготовки на следующую неделю"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  echo "- Базовый daily_ops отчет: $latest_daily"
  echo
  echo "## Обязательные исправления до начала недели"
  if [[ "${#integration_problems[@]}" -eq 0 ]]; then
    echo "1. Критичных проблем по интеграциям не обнаружено."
  else
    idx=1
    for item in "${integration_problems[@]}"; do
      echo "${idx}. ${item}"
      idx=$((idx + 1))
    done
  fi
  echo
  echo "## Проверки расписания и доставки"
  echo "1. Проверить, что ежедневный статус приходит до 09:30 Europe/Moscow."
  echo "2. Проверить доставку Telegram-статуса после daily_ops."
  echo "3. Проверить отсутствие пропусков по утреннему health-check за последние 7 дней."
  echo
  echo "## Команды на подготовку (one-click)"
  echo "1. DRY_RUN=0 make openclaw.daily-ops"
  echo "2. DRY_RUN=0 MODE=inspect make openclaw.healthcheck-schedule"
  echo "3. FAIL_ON_PROBLEMS=1 DRY_RUN=0 make openclaw.daily-ops"
  echo
  echo "## Сигналы риска из daily_ops"
  if [[ "${#daily_problems[@]}" -eq 0 ]]; then
    echo "- Не зафиксированы."
  else
    for line in "${daily_problems[@]}"; do
      echo "- ${line}"
    done
  fi
} >"$out_file"

echo "$out_file"
