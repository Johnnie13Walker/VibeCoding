#!/usr/bin/env bash
# Weekly refresh таба «Пустые компании».
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

WORKTREE="${WORKTREE:-$HOME/work-crm-enrich}"
MODULE_DIR="${MODULE_DIR:-$WORKTREE/belberry/bitrix24/crm_deal_merge}"
VENV="${VENV:-$WORKTREE/belberry/bitrix24/crm_company_enrich/.venv}"
LOG_DIR="${LOG_DIR:-$WORKTREE/belberry/bitrix24/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/empty_companies_cron.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/empty_companies_refresh.lock}"
SUMMARY_JSON="${SUMMARY_JSON:-/tmp/empty_companies_refresh_summary.json}"
MAX_ROWS="${MAX_ROWS:-12000}"

default_state="$WORKTREE/shared/config/bitrix24-state/install.latest.json"
default_sync="$WORKTREE/shared/scripts/bitrix-sync-state.sh"
default_sa="$HOME/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
[[ -f /opt/openclaw/state/bitrix_app/install.latest.json ]] && default_state="/opt/openclaw/state/bitrix_app/install.latest.json"
[[ -f /opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh ]] && default_sync="/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh"
[[ -f /opt/openclaw/secrets/finance-director-sheets-903611b799c3.json ]] && default_sa="/opt/openclaw/secrets/finance-director-sheets-903611b799c3.json"

export BITRIX_STATE_PATH="${BITRIX_STATE_PATH:-$default_state}"
export BITRIX_SYNC_SCRIPT="${BITRIX_SYNC_SCRIPT:-$default_sync}"
export GOOGLE_SA_KEY="${GOOGLE_SA_KEY:-$default_sa}"
export CRM_DEAL_MERGE_LOG_DIR="${CRM_DEAL_MERGE_LOG_DIR:-$LOG_DIR}"
export CRM_DEAL_MERGE_RATE_LIMIT_SLEEP_S="${CRM_DEAL_MERGE_RATE_LIMIT_SLEEP_S:-0.55}"

mkdir -p "$LOG_DIR"

rotate_log_weekly() {
  local week marker previous
  week="$(date +%G-W%V)"
  marker="$LOG_FILE.week"
  previous="$(cat "$marker" 2>/dev/null || true)"
  if [[ -n "$previous" && "$previous" != "$week" && -s "$LOG_FILE" ]]; then
    mv "$LOG_FILE" "$LOG_FILE.$previous"
    gzip -f "$LOG_FILE.$previous" || true
  fi
  printf '%s\n' "$week" > "$marker"
}

rotate_log_weekly
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] empty-companies refresh already running, exit" | tee -a "$LOG_FILE"
  exit 0
fi

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

run_python() {
  cd "$MODULE_DIR"
  PYTHONPATH="$MODULE_DIR" "$VENV/bin/python" "$@"
}

log "=== empty-companies refresh start ==="

if [[ -f "$BITRIX_SYNC_SCRIPT" ]]; then
  bash "$BITRIX_SYNC_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
fi

run_python -m crm_deal_merge.cli empty-companies-refresh \
  --live \
  --max-rows "$MAX_ROWS" \
  --summary-json "$SUMMARY_JSON" 2>&1 | tee -a "$LOG_FILE"

run_python scripts/audit_empty_company_duplicates.py 2>&1 | tee -a "$LOG_FILE"

if run_python scripts/notify_telegram.py --summary "$SUMMARY_JSON" 2>&1 | tee -a "$LOG_FILE"; then
  log "telegram notify OK"
else
  log "telegram notify failed (non-blocking)"
fi

log "=== empty-companies refresh OK ==="
