#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/remote-ops.env}"
SOURCE_FILE="${BITRIX_APP_SERVER_SOURCE_FILE:-$ROOT_DIR/server_snapshots/live_ams_1_vm_76ds_20260325/opt/openclaw/local/bitrix_app_server.py}"
REMOTE_PATH="${BITRIX_APP_SERVER_REMOTE_PATH:-/opt/openclaw/local/bitrix_app_server.py}"
REMOTE_TMP="${BITRIX_APP_SERVER_REMOTE_TMP:-/tmp/cloudbot_bitrix_app_server.py}"
APPLY="${BITRIX_APP_SERVER_DEPLOY_APPLY:-0}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ
: "${PYTHON_BIN:=python3}"
: "${PRIMARY_HOST:=${OPENCLAW_HOST:-}}"

if [[ -z "${PRIMARY_HOST:-}" ]]; then
  fail "Не задан PRIMARY_HOST/OPENCLAW_HOST для deploy Bitrix app server."
fi
if [[ ! -f "$SOURCE_FILE" ]]; then
  fail "Source file не найден: $SOURCE_FILE"
fi

STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REMOTE_TMP_STAMPED="${REMOTE_TMP%.py}_${STAMP}.py"

log "bitrix_app_server_deploy: source=${SOURCE_FILE}"
log "bitrix_app_server_deploy: target=${PRIMARY_HOST}:${REMOTE_PATH}, apply=${APPLY}"

"$PYTHON_BIN" -m py_compile "$SOURCE_FILE"

if [[ "$APPLY" != "1" ]]; then
  log "[DRY-RUN] Файл скомпилирован локально. Для deploy укажи BITRIX_APP_SERVER_DEPLOY_APPLY=1."
  exit 0
fi

require_env SSH_USER SSH_KEY_PATH SSH_PORT

scp -i "$SSH_KEY_PATH" -P "$SSH_PORT" \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 \
  "$SOURCE_FILE" "${SSH_USER}@${PRIMARY_HOST}:${REMOTE_TMP_STAMPED}"

remote_script=$(cat <<REMOTE
set -euo pipefail
remote_tmp="$REMOTE_TMP_STAMPED"
remote_path="$REMOTE_PATH"
backup_path="\${remote_path}.bak.$STAMP"

python3 -m py_compile "\$remote_tmp"
cp "\$remote_path" "\$backup_path"
chmod 600 "\$backup_path" || true
install -m 0644 "\$remote_tmp" "\$remote_path"

if ! systemctl restart cloudbot-bitrix-app.service; then
  cp "\$backup_path" "\$remote_path"
  systemctl restart cloudbot-bitrix-app.service || true
  echo "restart_failed_restored_backup=\$backup_path" >&2
  exit 1
fi

sleep 1
systemctl is-active --quiet cloudbot-bitrix-app.service
curl -fsS http://127.0.0.1:8787/healthz
printf "\\nbackup_path=%s\\n" "\$backup_path"
journalctl -u cloudbot-bitrix-app.service -n 30 --no-pager
REMOTE
)

run_remote_script "$PRIMARY_HOST" "$remote_script"
log "bitrix_app_server_deploy: успешно"
