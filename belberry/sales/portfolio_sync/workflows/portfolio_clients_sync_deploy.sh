#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/remote-ops.env}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/portfolio_clients_sync_deploy_${STAMP}.txt"

load_optional_env_file "$ENV_FILE"
require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

mkdir -p "$REPORT_DIR"

log "portfolio_clients_sync_deploy: старт"

{
  echo "# Portfolio Clients Sync Deploy"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${PRIMARY_HOST}"
  echo

  tar czf - \
    scripts/portfolio_clients_sync.mjs \
    scripts/run_portfolio_clients_daily.sh \
    scripts/install_portfolio_clients_server_cron.sh \
    | ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 \
      "${SSH_USER}@${PRIMARY_HOST}" \
      "set -euo pipefail
       tmp_dir=\$(mktemp -d /tmp/portfolio_clients_sync.XXXXXX)
       tar xzf - -C \"\$tmp_dir\"
       sudo -n bash \"\$tmp_dir/scripts/install_portfolio_clients_server_cron.sh\"
       sudo -n bash -n /opt/cloudbot-runtime/portfolio-clients/current/scripts/run_portfolio_clients_daily.sh
       sudo -n node --check /opt/cloudbot-runtime/portfolio-clients/current/scripts/portfolio_clients_sync.mjs
       rm -rf \"\$tmp_dir\"
       echo deploy=ok"
} | tee "$REPORT_FILE"

log "portfolio_clients_sync_deploy: успешно, отчет=${REPORT_FILE}"
