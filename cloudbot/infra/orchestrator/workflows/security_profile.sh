#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
PROFILE_SRC="${PROFILE_SRC:-$ROOT_DIR/infra/openclaw-security-profile.env.example}"
CHECK_SRC="${CHECK_SRC:-$ROOT_DIR/reports/host-security-check.sh.remote}"
REMOTE_PROFILE_PATH="${REMOTE_PROFILE_PATH:-/opt/openclaw/.env.security_profile}"
REMOTE_CHECK_PATH="${REMOTE_CHECK_PATH:-/usr/local/bin/host-security-check.sh}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

if [[ ! -f "$PROFILE_SRC" ]]; then
  fail "Не найден профиль: $PROFILE_SRC"
fi
if [[ ! -f "$CHECK_SRC" ]]; then
  fail "Не найден скрипт проверки: $CHECK_SRC"
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  log "[DRY-RUN] Хост: ${OPENCLAW_HOST}"
  log "[DRY-RUN] Профиль: ${PROFILE_SRC} -> ${REMOTE_PROFILE_PATH}"
  log "[DRY-RUN] Скрипт: ${CHECK_SRC} -> ${REMOTE_CHECK_PATH}"
  exit 0
fi

log "Выкладка security profile на хост ${OPENCLAW_HOST}"

profile_b64="$(base64 <"$PROFILE_SRC" | tr -d '\n')"
check_b64="$(base64 <"$CHECK_SRC" | tr -d '\n')"

remote_script=$(cat <<REMOTE
set -euo pipefail
mkdir -p "\$(dirname "$REMOTE_PROFILE_PATH")" "\$(dirname "$REMOTE_CHECK_PATH")"

if [[ ! -f "$REMOTE_PROFILE_PATH" ]]; then
  echo "$profile_b64" | base64 -d > "$REMOTE_PROFILE_PATH"
  chmod 600 "$REMOTE_PROFILE_PATH" || true
  echo "PROFILE_CREATED:$REMOTE_PROFILE_PATH"
else
  echo "PROFILE_EXISTS:$REMOTE_PROFILE_PATH"
fi

echo "$check_b64" | base64 -d > "$REMOTE_CHECK_PATH"
chmod +x "$REMOTE_CHECK_PATH"
bash -n "$REMOTE_CHECK_PATH"
echo "CHECK_DEPLOYED:$REMOTE_CHECK_PATH"
REMOTE
)

run_remote_script "$OPENCLAW_HOST" "$remote_script"
log "Выкладка завершена"
