#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

ROOT_DIR="${PORTFOLIO_DATABASE_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOG_DIR="${PORTFOLIO_DATABASE_LOG_DIR:-${ROOT_DIR}/tmp}"
SA_PATH="${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json}}}"

mkdir -p "$LOG_DIR"

cd "$ROOT_DIR"

GOOGLE_SERVICE_ACCOUNT_JSON="$SA_PATH" \
  node "${ROOT_DIR}/scripts/portfolio_database_refresh.mjs" \
  >> "${LOG_DIR}/portfolio_database_refresh.log" 2>&1

GOOGLE_SERVICE_ACCOUNT_JSON="$SA_PATH" \
  node "${ROOT_DIR}/scripts/portfolio_dashboard_refresh.mjs" \
  >> "${LOG_DIR}/portfolio_dashboard_refresh.log" 2>&1
