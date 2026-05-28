#!/usr/bin/env bash
# Cron wrapper: user-sync (Bitrix → Google Drive permissions) каждые 15 минут.
#
# crontab:
#   5,20,35,50 * * * * /home/cloudbot/VibeCoding/belberry/bitrix24/sales_dashboard/scripts/cron_user_sync.sh >> /var/log/sales_dashboard.user_sync.log 2>&1
set -euo pipefail

PROJECT_DIR="${SALES_DASHBOARD_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PYTHON_BIN="${SALES_DASHBOARD_PYTHON:-python3}"

cd "$PROJECT_DIR"

LOCK="$PROJECT_DIR/state/user_sync.lock"
mkdir -p "$(dirname "$LOCK")"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -Iseconds)] user-sync: previous run still alive, skip"
    exit 0
fi

echo "[$(date -Iseconds)] user-sync: start"
"$PYTHON_BIN" -m sales_dashboard.cli user-sync
RC=$?
echo "[$(date -Iseconds)] user-sync: end rc=$RC"
exit $RC
