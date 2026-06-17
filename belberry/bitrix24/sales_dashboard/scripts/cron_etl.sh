#!/usr/bin/env bash
# Cron wrapper: sales_dashboard ETL каждые 15 минут.
#
# Установка на VPS:
#   crontab -e
#   */15 * * * * /home/cloudbot/VibeCoding/belberry/bitrix24/sales_dashboard/scripts/cron_etl.sh >> /var/log/sales_dashboard.cron.log 2>&1
set -euo pipefail

# абсолютный путь к проекту (правится при деплое)
PROJECT_DIR="${SALES_DASHBOARD_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PYTHON_BIN="${SALES_DASHBOARD_PYTHON:-python3}"

cd "$PROJECT_DIR"

# Lock чтобы две копии не залезли в одни и те же листы одновременно.
LOCK="$PROJECT_DIR/state/etl.lock"
mkdir -p "$(dirname "$LOCK")"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -Iseconds)] etl: previous run still alive, skip"
    exit 0
fi

echo "[$(date -Iseconds)] etl: start"
"$PYTHON_BIN" -m sales_dashboard.cli etl
RC=$?
echo "[$(date -Iseconds)] etl: end rc=$RC"
exit $RC
