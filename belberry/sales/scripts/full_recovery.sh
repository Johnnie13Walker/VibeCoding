#!/usr/bin/env bash
# Полный recovery: force-refresh OAuth → manual boevoy dispatch.
# Запуск на проде:
#   bash full_recovery.sh             # отправит в боевой chat_id (тот же, что у cron)
#   DRY_CHAT_ID=<id> bash full_recovery.sh   # отправит в тестовый
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=== STEP 1: force OAuth refresh ==="
bash "$SCRIPT_DIR/force_refresh.sh"
echo
echo "=== STEP 2: manual sales dispatch ==="

cd /opt/cloudbot-runtime/current
set -a
. /opt/openclaw/.env
. /etc/openclaw/sales_agent.env
set +a
export TZ=Europe/Moscow
export SALES_TRIGGER=manual_recovery
export SALES_JOB_NAME=morning_sales_dispatch

if [ -n "${DRY_CHAT_ID:-}" ]; then
  echo "DRY MODE: SALES_DAILY_OWNER_CHAT_ID overridden to $DRY_CHAT_ID"
  export SALES_DAILY_OWNER_CHAT_ID="$DRY_CHAT_ID"
  export SALES_CHAT_ID="$DRY_CHAT_ID"
fi

TS=$(date '+%Y%m%d_%H%M%S')
REPORT="/home/ops/cloudbot-sales-agent/reports/sales_manual_recovery_${TS}_MSK.txt"
echo "Output -> $REPORT"

python3 -m agents.lev_petrovich --report sales --send 2>&1 | tee "$REPORT"

echo
echo "=== STEP 3: last 10 sales_agent.log events ==="
tail -n 10 /home/ops/cloudbot-sales-agent/reports/sales_agent.log
