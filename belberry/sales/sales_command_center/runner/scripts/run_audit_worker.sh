#!/usr/bin/env bash
# Воркер аудита сделок: подхватывает pending-задания deal_audits (страница /audit)
# и прогоняет audit_engine. Интерактивный — запускать часто (раз в минуту в раб. время).
# SCC_AUDIO=1 включает расшифровку звонков/видео (нужен faster-whisper).
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

SCC_AUDIT_LOCK="${SCC_AUDIT_LOCK:-/tmp/scc-audit-worker.lock}"
SCC_LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$SCC_LOG_DIR"
LOG="$SCC_LOG_DIR/audit-worker-$(date +%F).log"

exec 9>"$SCC_AUDIT_LOCK"
flock -n 9 || exit 0  # предыдущий проход ещё идёт — тихо выходим

cd "$RUNNER_DIR"
.venv/bin/python -m src.audit_worker --once >>"$LOG" 2>&1 \
  || echo "$(date -Is) audit_worker WARN" >>"$LOG"
