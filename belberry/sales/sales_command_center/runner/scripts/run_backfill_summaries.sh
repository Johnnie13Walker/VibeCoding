#!/usr/bin/env bash
# Дозачёт «итоги встречи отправлены клиенту» по пост-встречной переписке (Wazzup/письма
# ПОСЛЕ встречи). Ловит итоги, отправленные ПОЗЖЕ разбора встречи (разбор идемпотентен,
# late-итоги иначе не засчитываются). Скользящее окно 7 дней, идемпотентно (уже
# зачтённые summary_sent=true выпадают из кандидатов). Раз в сутки из cron.
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

SCC_BACKFILL_LOCK="${SCC_BACKFILL_LOCK:-/tmp/scc-backfill-summaries.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
SCC_BACKFILL_DAYS="${SCC_BACKFILL_DAYS:-7}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/backfill-summaries-$(date +%F).log"

exec 9>"$SCC_BACKFILL_LOCK"
flock -n 9 || {
  echo "$(date -Is) backfill_summaries уже выполняется, пропуск" >>"$LOG"
  exit 0
}

cd "$RUNNER_DIR"
echo "$(date -Is) backfill_summaries START (окно ${SCC_BACKFILL_DAYS} дн.)" >>"$LOG"
.venv/bin/python -m src.backfill_meeting_summaries --days "$SCC_BACKFILL_DAYS" --live >>"$LOG" 2>&1 \
  || echo "$(date -Is) backfill_summaries WARN" >>"$LOG"
echo "$(date -Is) backfill_summaries DONE" >>"$LOG"
