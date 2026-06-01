#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

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

echo "$(date -Is) старт daily_runner" >>"$LOG"
"$RUNNER_DIR/.venv/bin/python" "$RUNNER_DIR/daily_runner.py" >>"$LOG" 2>&1
echo "$(date -Is) daily_runner завершён" >>"$LOG"
