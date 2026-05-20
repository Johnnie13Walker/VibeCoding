#!/usr/bin/env bash
set -euo pipefail

source /opt/openclaw/.env
source /etc/openclaw/larisa.env

export TZ=Europe/Moscow
export LARISA_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
export LARISA_TELEGRAM_CHAT_ID="$LARISA_TELEGRAM_CHAT_ID"
export GOOGLE_SA_KEY="${GOOGLE_SA_KEY:-/opt/openclaw/secrets/finance-director-sheets-903611b799c3.json}"
export BITRIX_STATE_PATH="${BITRIX_STATE_PATH:-/opt/openclaw/state/bitrix_app/install.latest.json}"
export BITRIX_SYNC_SCRIPT="${BITRIX_SYNC_SCRIPT:-/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh}"

exec /opt/cloudbot-runtime/larisa/sales-kpi-dashboard/sales_kpi_dashboard/scripts/cron_refresh.sh
