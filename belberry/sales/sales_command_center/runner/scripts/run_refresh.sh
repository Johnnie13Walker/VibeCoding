#!/usr/bin/env bash
# Частый refresh данных за сегодня (дашборды/вкладки) + причины отвала + названия
# сделок. БЕЗ LLM/Telegram/отчёта. Запуск из cron каждые 20 мин в рабочее время.
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

SCC_REFRESH_LOCK="${SCC_REFRESH_LOCK:-/tmp/scc-refresh.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/refresh-$(date +%F).log"

exec 9>"$SCC_REFRESH_LOCK"
flock -n 9 || {
  echo "$(date -Is) refresh уже выполняется, пропуск" >>"$LOG"
  exit 0
}

cd "$RUNNER_DIR"
echo "$(date -Is) refresh START" >>"$LOG"
.venv/bin/python -m src.refresh_runner   >>"$LOG" 2>&1 || echo "$(date -Is) refresh_runner WARN"   >>"$LOG"
.venv/bin/python -m src.sync_rejections  >>"$LOG" 2>&1 || echo "$(date -Is) sync_rejections WARN"  >>"$LOG"
.venv/bin/python -m src.sync_wins        >>"$LOG" 2>&1 || echo "$(date -Is) sync_wins WARN"        >>"$LOG"
.venv/bin/python -m src.sync_deal_titles >>"$LOG" 2>&1 || echo "$(date -Is) sync_deal_titles WARN" >>"$LOG"
.venv/bin/python -m src.sync_payments    >>"$LOG" 2>&1 || echo "$(date -Is) sync_payments WARN"    >>"$LOG"
.venv/bin/python -m src.sync_users_active >>"$LOG" 2>&1 || echo "$(date -Is) sync_users_active WARN" >>"$LOG"
.venv/bin/python -m src.sync_absences      >>"$LOG" 2>&1 || echo "$(date -Is) sync_absences WARN"      >>"$LOG"
echo "$(date -Is) refresh DONE" >>"$LOG"
