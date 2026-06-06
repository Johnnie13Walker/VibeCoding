#!/usr/bin/env bash
# Инкрементальный LLM-разбор новых встреч (только непроанализированные за последние
# дни). Без отчёта/Telegram. Запуск из cron раз в час в рабочее время.
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

SCC_ANALYZE_LOCK="${SCC_ANALYZE_LOCK:-/tmp/scc-analyze-pending.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/analyze-pending-$(date +%F).log"

exec 9>"$SCC_ANALYZE_LOCK"
flock -n 9 || {
  echo "$(date -Is) analyze_pending уже выполняется, пропуск" >>"$LOG"
  exit 0
}

cd "$RUNNER_DIR"
echo "$(date -Is) analyze_pending START" >>"$LOG"
.venv/bin/python -m src.analyze_pending --days 3 >>"$LOG" 2>&1 \
  || echo "$(date -Is) analyze_pending WARN" >>"$LOG"
echo "$(date -Is) analyze_pending DONE" >>"$LOG"
