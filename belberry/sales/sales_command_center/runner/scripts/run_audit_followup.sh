#!/usr/bin/env bash
# Петля отслеживания возврата: через N дней проверяет, двинулась ли сделка. Раз в день.
set -euo pipefail
export TZ="${TZ:-Europe/Moscow}"
SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
[ -f "$SCC_ENV_FILE" ] && { set -a; . "$SCC_ENV_FILE"; set +a; }
LOCK="${SCC_FOLLOWUP_LOCK:-/tmp/scc-audit-followup.lock}"
LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"; mkdir -p "$LOG_DIR"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec 9>"$LOCK"; flock -n 9 || exit 0
cd "$RUNNER_DIR"
.venv/bin/python -m src.audit_followup >> "$LOG_DIR/audit-followup-$(date +%F).log" 2>&1 \
  || echo "$(date -Is) audit_followup WARN" >> "$LOG_DIR/audit-followup-$(date +%F).log"
