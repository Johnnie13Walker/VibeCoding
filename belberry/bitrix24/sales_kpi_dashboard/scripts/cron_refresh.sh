#!/usr/bin/env bash
# Cron wrapper для sales_kpi_dashboard refresh.
# Запускается из cron 0 3,7,11,15 * * * UTC = 06/10/14/18 МСК.
set -euo pipefail

LOG_DIR="${LOG_DIR:-/var/log}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/cloudbot-larisa-sales-kpi.log}"
JOB_ROOT="${JOB_ROOT:-/opt/cloudbot-runtime/larisa/sales-kpi-dashboard}"
SALES_DASHBOARD_DIR="${SALES_DASHBOARD_DIR:-$JOB_ROOT/sales_dashboard}"
KPI_DIR="${KPI_DIR:-$JOB_ROOT/sales_kpi_dashboard}"
VENV="${VENV:-$JOB_ROOT/.venv}"
BITRIX_STATE="${BITRIX_STATE:-/opt/openclaw/state/bitrix_app/install.latest.json}"
BITRIX_SYNC_SCRIPT="${BITRIX_SYNC_SCRIPT:-/opt/cloudbot-runtime/shared/scripts/bitrix-sync-state.sh}"
GOOGLE_SA_KEY="${GOOGLE_SA_KEY:-/opt/openclaw/secrets/finance-director-sheets-903611b799c3.json}"
LOCK_FILE="${LOCK_FILE:-/tmp/sales_kpi.lock}"

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] sales_kpi refresh already running, exit" | tee -a "$LOG_FILE"
  exit 0
fi

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

run_refresh() {
  cd "$KPI_DIR"
  BITRIX_STATE_PATH="$BITRIX_STATE" BITRIX_SYNC_SCRIPT="$BITRIX_SYNC_SCRIPT" GOOGLE_SA_KEY="$GOOGLE_SA_KEY" PYTHONPATH="$SALES_DASHBOARD_DIR" \
    "$VENV/bin/python" -m sales_kpi_dashboard.cli refresh 2>&1 | tee -a "$LOG_FILE"
  return "${PIPESTATUS[0]}"
}

log "=== sales_kpi refresh start ==="

if run_refresh; then
  log "refresh OK"
  exit 0
fi

log "refresh failed, trying to sync Bitrix state..."
if [[ -x "$BITRIX_SYNC_SCRIPT" ]]; then
  if "$BITRIX_SYNC_SCRIPT" 2>&1 | tee -a "$LOG_FILE"; then
    log "state synced, retrying refresh..."
    if run_refresh; then
      log "refresh OK after sync"
      exit 0
    fi
  else
    log "Bitrix state sync failed"
  fi
else
  log "Bitrix sync script not executable: $BITRIX_SYNC_SCRIPT"
fi

log "refresh FAILED"
BITRIX_STATE_PATH="$BITRIX_STATE" BITRIX_SYNC_SCRIPT="$BITRIX_SYNC_SCRIPT" GOOGLE_SA_KEY="$GOOGLE_SA_KEY" PYTHONPATH="$SALES_DASHBOARD_DIR" \
  "$VENV/bin/python" -m sales_kpi_dashboard.cli sync-log-error \
  --phase "phase 4" \
  --error "cron_refresh failed after retry" 2>&1 | tee -a "$LOG_FILE" || log "sync-log-error failed (non-blocking)"

log "=== alert-check ==="
BITRIX_STATE_PATH="$BITRIX_STATE" BITRIX_SYNC_SCRIPT="$BITRIX_SYNC_SCRIPT" GOOGLE_SA_KEY="$GOOGLE_SA_KEY" PYTHONPATH="$SALES_DASHBOARD_DIR" \
  "$VENV/bin/python" -m sales_kpi_dashboard.cli alert-check 2>&1 | tee -a "$LOG_FILE" || log "alert-check failed (non-blocking)"
exit 1
