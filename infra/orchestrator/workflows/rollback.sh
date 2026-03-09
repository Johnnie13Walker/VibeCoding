#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST

rollback_node() {
  local host="$1"
  local node_name="$2"

  log "Rollback узла ${node_name} (${host})"
  run_remote_script "$host" "
set -euo pipefail
latest_backup=\$(ls -1dt /etc/happ-vpn/backups/${node_name}_* 2>/dev/null | head -n1)
if [ -z \"\${latest_backup:-}\" ]; then
  echo 'Нет backup для rollback'
  exit 1
fi
if [ -d \"\$latest_backup/sing-box\" ]; then
  rm -rf /etc/sing-box
  cp -a \"\$latest_backup/sing-box\" /etc/sing-box
fi
systemctl restart sing-box || true
"
}

rollback_node "$PRIMARY_HOST" "${PRIMARY_NODE_NAME:-happ-main}"
if [[ -n "${RESERVE_HOST:-}" ]]; then
  rollback_node "$RESERVE_HOST" "${RESERVE_NODE_NAME:-happ-backup}"
fi

log "Rollback workflow завершен"
