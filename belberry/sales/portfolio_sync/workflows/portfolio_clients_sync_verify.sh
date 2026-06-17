#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/remote-ops.env}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/portfolio_clients_sync_verify_${STAMP}.txt"

load_optional_env_file "$ENV_FILE"
require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

mkdir -p "$REPORT_DIR"

log "portfolio_clients_sync_verify: старт"

run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow
root_dir='/opt/cloudbot-runtime/portfolio-clients/current'
test -x \"\$root_dir/scripts/run_portfolio_clients_daily.sh\"
test -x \"\$root_dir/scripts/portfolio_clients_sync.mjs\"
test -f /etc/cron.d/cloudbot-portfolio-clients
node --check \"\$root_dir/scripts/portfolio_clients_sync.mjs\"
PORTFOLIO_CLIENTS_REPORT_JSON=\"\$root_dir/tmp/portfolio_clients_sync.verify.json\" \
  \"\$root_dir/run_portfolio_clients_from_server_env.sh\" \
  node \"\$root_dir/scripts/portfolio_clients_sync.mjs\" --dry-run --report-json \"\$root_dir/tmp/portfolio_clients_sync.verify.json\"
echo
echo '# cron'
cat /etc/cron.d/cloudbot-portfolio-clients
echo
echo '# report'
cat \"\$root_dir/tmp/portfolio_clients_sync.verify.json\"
" | tee "$REPORT_FILE"

log "portfolio_clients_sync_verify: успешно, отчет=${REPORT_FILE}"
