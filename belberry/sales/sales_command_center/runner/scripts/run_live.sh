#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

# Лёгкий сбор «Сегодня» (без Wazzup/LLM) — частый cron. Env из сервисного файла.
SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

# Отдельный lock от daily-раннера.
SCC_LIVE_LOCK="${SCC_LIVE_LOCK:-/tmp/scc-live.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/live-$(date +%F).log"

exec 9>"$SCC_LIVE_LOCK"
flock -n 9 || {
  echo "$(date -Is) live уже выполняется, пропуск" >>"$LOG"
  exit 0
}
export SCC_LOCK_FD=9

"$RUNNER_DIR/.venv/bin/python" "$RUNNER_DIR/live_runner.py" >>"$LOG" 2>&1
