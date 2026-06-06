#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

# У cron нет окружения сервиса — подгружаем env-файл (DATABASE_URL/SCC_*/TELEGRAM_*),
# иначе автозапуск падает на отсутствии переменных. Путь переопределяется SCC_ENV_FILE.
SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

SCC_LOCK_PATH="${SCC_LOCK_PATH:-/tmp/scc-daily-runner.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/daily-$(date +%F).log"

exec 9>"$SCC_LOCK_PATH"
flock -n 9 || {
  echo "$(date -Is) уже выполняется, пропуск" >>"$LOG"
  exit 0
}
export SCC_LOCK_FD=9

echo "$(date -Is) старт daily_runner" >>"$LOG"
"$RUNNER_DIR/.venv/bin/python" "$RUNNER_DIR/daily_runner.py" >>"$LOG" 2>&1
echo "$(date -Is) daily_runner завершён" >>"$LOG"

# Свежесть событийного слоя отвалов ТМ (deal_rejections не в основном пайплайне).
# Не критично для отчёта — при сбое не валим прогон.
echo "$(date -Is) старт sync_rejections" >>"$LOG"
( cd "$RUNNER_DIR" && "$RUNNER_DIR/.venv/bin/python" -m src.sync_rejections ) >>"$LOG" 2>&1 \
  || echo "$(date -Is) sync_rejections WARN (не критично, отчёт уже готов)" >>"$LOG"
echo "$(date -Is) sync_rejections завершён" >>"$LOG"
