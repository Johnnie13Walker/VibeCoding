#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OUT_DIR="${OUT_DIR:-$REPORT_DIR/high_leverage}"

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "$OUT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
OUT_FILE="$OUT_DIR/high_leverage_24h_${STAMP}.md"

latest_daily="$(ls -1t "$REPORT_DIR"/daily_ops_*_MSK.txt 2>/dev/null | head -n1 || true)"
step_title="Ужесточить ежедневный контроль до fail-fast"
step_command="FAIL_ON_PROBLEMS=1 SEND_TELEGRAM_STATUS=always DRY_RUN=0 make openclaw.daily-ops"
step_why="Это превращает контроль из наблюдения в обязательный gate и сразу подсвечивает недоставку/инцидент."

if [[ -n "$latest_daily" ]] && grep -q "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы" "$latest_daily"; then
  step_title="Закрыть доставку статуса в Telegram и включить жесткий fail"
  step_command="(1) заполнить TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID в .env.integrations; (2) FAIL_ON_PROBLEMS=1 SEND_TELEGRAM_STATUS=always DRY_RUN=0 make openclaw.daily-ops"
  step_why="Без рабочей доставки ежедневный контроль не достигает владельца вовремя."
fi

{
  echo "# High-Leverage Шаг на 24 часа (MSK)"
  echo
  echo "- Сформировано: $(date '+%F %T %Z')"
  if [[ -n "$latest_daily" ]]; then
    echo "- Основано на: $latest_daily"
  fi
  echo
  echo "## Один шаг"
  echo "1. ${step_title}"
  echo
  echo "## Команда/действие"
  echo "1. ${step_command}"
  echo
  echo "## Почему это максимум эффекта"
  echo "1. ${step_why}"
  echo
  echo "## Критерий успеха"
  echo "1. Есть свежий daily_ops отчет и статус доставлен."
  echo "2. При проблеме workflow завершился с не-нулевым кодом."
} >"$OUT_FILE"

echo "$OUT_FILE"
