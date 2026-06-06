#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

# Отдельный lock от daily и light-live.
SCC_WZ_LOCK="${SCC_WZ_LOCK:-/tmp/scc-live-wazzup.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/live-wazzup-$(date +%F).log"

exec 9>"$SCC_WZ_LOCK"
flock -n 9 || {
  echo "$(date -Is) live-wazzup уже выполняется, пропуск" >>"$LOG"
  exit 0
}
export SCC_LOCK_FD=9

"$RUNNER_DIR/.venv/bin/python" "$RUNNER_DIR/live_wazzup_runner.py" >>"$LOG" 2>&1
