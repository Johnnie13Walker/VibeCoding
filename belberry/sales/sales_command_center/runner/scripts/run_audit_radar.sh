#!/usr/bin/env bash
# Радар застрявших сделок → авто-аудиты (раз в день). Дёшев (REST-сканы + INSERT),
# реальные разборы делает воркер аудита. flock от наложения.
set -euo pipefail
export TZ="${TZ:-Europe/Moscow}"
SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
[ -f "$SCC_ENV_FILE" ] && { set -a; . "$SCC_ENV_FILE"; set +a; }
LOCK="${SCC_RADAR_LOCK:-/tmp/scc-audit-radar.lock}"
LOG_DIR="${SCC_LOG_DIR:-/var/log/scc}"; mkdir -p "$LOG_DIR"
RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec 9>"$LOCK"; flock -n 9 || exit 0
cd "$RUNNER_DIR"
.venv/bin/python -m src.audit_radar >> "$LOG_DIR/audit-radar-$(date +%F).log" 2>&1 \
  || echo "$(date -Is) audit_radar WARN" >> "$LOG_DIR/audit-radar-$(date +%F).log"
