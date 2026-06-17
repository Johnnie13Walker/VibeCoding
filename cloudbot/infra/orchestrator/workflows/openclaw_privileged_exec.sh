#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
MODE="${1:-inspect}"
ACTION="${ACTION:-status}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
HELPER_USER="${HELPER_USER:-ops}"
HELPER_PATH="${HELPER_PATH:-/usr/local/sbin/openclaw-update-helper}"
PKG_MANAGER="${PKG_MANAGER:-npm}"
CHANNEL="${CHANNEL:-stable}"
RAW_CMD="${RAW_CMD:-}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

case "$ACTION" in
  status|install-global|doctor|gateway-restart|openclaw-update|all|raw) ;;
  *)
    fail "Неизвестный ACTION: $ACTION (доступно: status, install-global, doctor, gateway-restart, openclaw-update, all, raw)"
    ;;
esac

if [[ "$ACTION" == "install-global" && "$PKG_MANAGER" != "npm" && "$PKG_MANAGER" != "pnpm" ]]; then
  fail "PKG_MANAGER должен быть npm или pnpm"
fi

if [[ "$ACTION" == "raw" && -z "$RAW_CMD" ]]; then
  fail "Для ACTION=raw требуется RAW_CMD"
fi

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/openclaw_privileged_exec_${STAMP}.txt"

mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"
action_b64="$(printf '%s' "$ACTION" | base64 | tr -d '\n')"
helper_user_b64="$(printf '%s' "$HELPER_USER" | base64 | tr -d '\n')"
helper_path_b64="$(printf '%s' "$HELPER_PATH" | base64 | tr -d '\n')"
pkg_manager_b64="$(printf '%s' "$PKG_MANAGER" | base64 | tr -d '\n')"
channel_b64="$(printf '%s' "$CHANNEL" | base64 | tr -d '\n')"
raw_cmd_b64="$(printf '%s' "$RAW_CMD" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
action="$(printf '%s' '__ACTION_B64__' | base64 -d)"
helper_user="$(printf '%s' '__HELPER_USER_B64__' | base64 -d)"
helper_path="$(printf '%s' '__HELPER_PATH_B64__' | base64 -d)"
pkg_manager="$(printf '%s' '__PKG_MANAGER_B64__' | base64 -d)"
channel="$(printf '%s' '__CHANNEL_B64__' | base64 -d)"
raw_cmd="$(printf '%s' '__RAW_CMD_B64__' | base64 -d)"

if [ ! -x "${helper_path}" ]; then
  echo "ОШИБКА: helper не найден или не исполняемый: ${helper_path}" >&2
  exit 1
fi

declare -a helper_cmd
case "${action}" in
  status)
    helper_cmd=("${helper_path}" "status")
    ;;
  install-global)
    helper_cmd=("${helper_path}" "install-openclaw-global" "${pkg_manager}")
    ;;
  doctor)
    helper_cmd=("${helper_path}" "doctor")
    ;;
  gateway-restart)
    helper_cmd=("${helper_path}" "gateway-restart")
    ;;
  openclaw-update)
    helper_cmd=("${helper_path}" "openclaw" "${channel}")
    ;;
  all)
    helper_cmd=("${helper_path}" "all" "${channel}")
    ;;
  raw)
    helper_cmd=("${helper_path}" "raw" "${raw_cmd}")
    ;;
  *)
    echo "ОШИБКА: неподдерживаемое действие: ${action}" >&2
    exit 2
    ;;
esac

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=${mode}"
echo "action=${action}"
echo "helper_user=${helper_user}"
echo "helper_path=${helper_path}"
echo "pkg_manager=${pkg_manager}"
echo "channel=${channel}"
if [ "${action}" = "raw" ]; then
  echo "raw_cmd=${raw_cmd}"
fi
printf 'helper_cmd='
printf '%q ' "${helper_cmd[@]}"
echo

if [ "${mode}" = "inspect" ]; then
  exit 0
fi

if id "${helper_user}" >/dev/null 2>&1; then
  sudo -u "${helper_user}" -n sudo -n "${helper_cmd[@]}"
else
  sudo -n "${helper_cmd[@]}"
fi
REMOTE

remote_script="${remote_script/__MODE_B64__/$mode_b64}"
remote_script="${remote_script/__ACTION_B64__/$action_b64}"
remote_script="${remote_script/__HELPER_USER_B64__/$helper_user_b64}"
remote_script="${remote_script/__HELPER_PATH_B64__/$helper_path_b64}"
remote_script="${remote_script/__PKG_MANAGER_B64__/$pkg_manager_b64}"
remote_script="${remote_script/__CHANNEL_B64__/$channel_b64}"
remote_script="${remote_script/__RAW_CMD_B64__/$raw_cmd_b64}"

log "Запуск workflow openclaw_privileged_exec: mode=${MODE}, host=${OPENCLAW_HOST}, action=${ACTION}"
{
  echo "# OpenClaw Privileged Exec"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${OPENCLAW_HOST}"
  echo "Режим: ${MODE}"
  echo "Действие: ${ACTION}"
  echo
  run_remote_script "$OPENCLAW_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "Workflow openclaw_privileged_exec завершён"
log "Отчет: ${REPORT_FILE}"
