#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
BOT_UPDATE_USERS="${BOT_UPDATE_USERS:-node}"
HELPER_PATH="${HELPER_PATH:-/usr/local/sbin/openclaw-update-helper}"
SUDOERS_PATH="${SUDOERS_PATH:-/etc/sudoers.d/openclaw-update-helper}"
MODE="${1:-inspect}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

helper_payload=""
read -r -d '' helper_payload <<'HELPER' || true
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_NODE="${OPENCLAW_NODE:-node}"
OPENCLAW_RUNNER="${OPENCLAW_RUNNER:-scripts/run-node.mjs}"

strip_ansi() {
  sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g'
}

run_openclaw() {
  if [ -f "${OPENCLAW_DIR}/dist/entry.js" ]; then
    (cd "${OPENCLAW_DIR}" && OPENCLAW_RUNNER_LOG=0 "${OPENCLAW_NODE}" dist/entry.js "$@")
    return $?
  fi
  if [ -f "${OPENCLAW_DIR}/${OPENCLAW_RUNNER}" ]; then
    (cd "${OPENCLAW_DIR}" && OPENCLAW_RUNNER_LOG=0 "${OPENCLAW_NODE}" "${OPENCLAW_RUNNER}" "$@")
    return $?
  fi
  if command -v openclaw >/dev/null 2>&1; then
    openclaw "$@"
    return $?
  fi
  echo "ОШИБКА: OpenClaw CLI не найден" >&2
  return 1
}

collect_security_packages() {
  apt list --upgradable 2>/dev/null | awk -F/ 'NR>1 && tolower($0) ~ /security/ {print $1}' | sort -u
}

usage() {
  cat <<'USAGE'
Использование: sudo openclaw-update-helper <status|os-security|os-all|openclaw|install-openclaw-global|doctor|gateway-restart|all|raw>
  status                  Показать pending updates по ОС и OpenClaw
  os-security             Применить только security-обновления ОС
  os-all                  Применить все обновления ОС (apt upgrade)
  openclaw [channel]      Обновить OpenClaw (по умолчанию stable)
  install-openclaw-global Установить/обновить OpenClaw глобально (npm|pnpm)
  doctor                  Запустить openclaw doctor --non-interactive
  gateway-restart         Перезапустить openclaw gateway
  all [channel]           os-security + openclaw
  raw "<command>"         Выполнить одну разрешенную root-команду по allowlist
USAGE
}

update_openclaw() {
  local channel="${1:-stable}" out rc
  for attempt in \
    "update apply --channel ${channel} --yes" \
    "update --channel ${channel} --yes" \
    "update apply --channel ${channel}" \
    "update --channel ${channel}" \
    "update apply" \
    "update"
  do
    set +e
    out="$(run_openclaw ${attempt} 2>&1)"
    rc=$?
    set -e
    printf '[openclaw-update] attempt="%s" rc=%s\n' "${attempt}" "${rc}"
    printf '%s\n' "${out}" | strip_ansi
    if [ "${rc}" -eq 0 ]; then
      return 0
    fi
  done
  return 1
}

run_raw_update_command() {
  local raw_cmd="$1"
  if [ -z "${raw_cmd}" ]; then
    echo "ОШИБКА: команда не передана" >&2
    return 2
  fi
  if printf '%s' "${raw_cmd}" | grep -Eq '[;&|<>`$()]'; then
    echo "ОШИБКА: запрещены управляющие символы shell в raw-команде" >&2
    return 2
  fi
  if ! printf '%s' "${raw_cmd}" | grep -Eqi '^((apt|apt-get|unattended-upgrade)([[:space:]]+.*)?|((/usr/local/bin/)?openclaw)[[:space:]]+update([[:space:]]+.*)?|((/usr/local/bin/)?openclaw)[[:space:]]+doctor([[:space:]]+--non-interactive)?|((/usr/local/bin/)?openclaw)[[:space:]]+gateway[[:space:]]+restart|pnpm[[:space:]]+add[[:space:]]+-g[[:space:]]+openclaw(@latest)?|npm[[:space:]]+i(nstall)?[[:space:]]+-g[[:space:]]+openclaw(@latest)?|systemctl[[:space:]]+(restart|status)[[:space:]]+openclaw([-.[:alnum:]]+)?|docker[[:space:]]+restart[[:space:]]+openclaw[-_.[:alnum:]]+)$'; then
    echo "ОШИБКА: команда не входит в безопасный allowlist (update/doctor/restart/install)" >&2
    return 2
  fi
  bash -lc "${raw_cmd}"
}

cmd="${1:-status}"
shift || true

case "${cmd}" in
  status)
    echo "=== OS upgradable ==="
    apt list --upgradable 2>/dev/null || true
    echo "=== OS security packages ==="
    collect_security_packages || true
    echo "=== OpenClaw update status ==="
    run_openclaw update status 2>&1 | strip_ansi || true
    ;;
  os-security)
    mapfile -t sec_pkgs < <(collect_security_packages)
    if [ "${#sec_pkgs[@]}" -eq 0 ]; then
      echo "security_updates=none"
      exit 0
    fi
    echo "security_updates=${sec_pkgs[*]}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y --only-upgrade --allow-change-held-packages "${sec_pkgs[@]}"
    ;;
  os-all)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y
    ;;
  openclaw)
    update_openclaw "${1:-stable}"
    ;;
  install-openclaw-global)
    case "${1:-npm}" in
      npm)
        npm i -g openclaw@latest
        ;;
      pnpm)
        pnpm add -g openclaw@latest
        ;;
      *)
        echo "ОШИБКА: install-openclaw-global поддерживает только npm|pnpm" >&2
        exit 2
        ;;
    esac
    ;;
  doctor)
    run_openclaw doctor --non-interactive
    ;;
  gateway-restart)
    run_openclaw gateway restart
    ;;
  all)
    channel="${1:-stable}"
    "$0" os-security
    "$0" openclaw "${channel}"
    ;;
  raw)
    run_raw_update_command "${*:-}"
    ;;
  *)
    usage
    exit 2
    ;;
esac
HELPER

users_b64="$(printf '%s' "$BOT_UPDATE_USERS" | base64 | tr -d '\n')"
helper_path_b64="$(printf '%s' "$HELPER_PATH" | base64 | tr -d '\n')"
sudoers_path_b64="$(printf '%s' "$SUDOERS_PATH" | base64 | tr -d '\n')"
mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"
helper_payload_b64="$(printf '%s' "$helper_payload" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

users_raw="$(printf '%s' '__USERS_B64__' | base64 -d)"
helper_path="$(printf '%s' '__HELPER_B64__' | base64 -d)"
sudoers_path="$(printf '%s' '__SUDOERS_B64__' | base64 -d)"
mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
helper_payload_b64='__HELPER_PAYLOAD_B64__'

read -r -a requested_users <<< "$users_raw"
existing_users=()
for u in "${requested_users[@]}"; do
  if id "$u" >/dev/null 2>&1; then
    existing_users+=("$u")
  fi
done

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=${mode}"
echo "requested_users=${users_raw}"
echo "existing_users=${existing_users[*]:-<none>}"
echo "helper_path=${helper_path}"
echo "sudoers_path=${sudoers_path}"

if [ "${mode}" = "inspect" ]; then
  if [ -f "${helper_path}" ]; then
    echo "helper_present=1 perms=$(stat -c '%U:%G %a' "${helper_path}" 2>/dev/null || echo unknown)"
  else
    echo "helper_present=0"
  fi
  if [ -f "${sudoers_path}" ]; then
    echo "sudoers_present=1"
    sed -n '1,120p' "${sudoers_path}" || true
    visudo -cf "${sudoers_path}" || true
  else
    echo "sudoers_present=0"
  fi
  exit 0
fi

if [ "${#existing_users[@]}" -eq 0 ]; then
  echo "ОШИБКА: среди BOT_UPDATE_USERS не найдено ни одного существующего пользователя" >&2
  exit 1
fi

mkdir -p "$(dirname "${helper_path}")" "$(dirname "${sudoers_path}")"

tmp_helper="$(mktemp)"
printf '%s' "${helper_payload_b64}" | base64 -d >"${tmp_helper}"
install -o root -g root -m 0750 "${tmp_helper}" "${helper_path}"
rm -f "${tmp_helper}"

tmp_sudoers="$(mktemp)"
{
  echo "# Managed by infra/orchestrator/workflows/openclaw_update_permissions.sh"
  for u in "${existing_users[@]}"; do
    echo "${u} ALL=(root) NOPASSWD: ${helper_path} *"
  done
} >"${tmp_sudoers}"

chmod 0440 "${tmp_sudoers}"
visudo -cf "${tmp_sudoers}"
install -o root -g root -m 0440 "${tmp_sudoers}" "${sudoers_path}"
rm -f "${tmp_sudoers}"
visudo -cf "${sudoers_path}"

echo "apply_result=ok"
echo "helper_perms=$(stat -c '%U:%G %a' "${helper_path}" 2>/dev/null || echo unknown)"
echo "sudoers_perms=$(stat -c '%U:%G %a' "${sudoers_path}" 2>/dev/null || echo unknown)"
echo "allowed_users=${existing_users[*]}"
REMOTE

remote_script="${remote_script/__USERS_B64__/$users_b64}"
remote_script="${remote_script/__HELPER_B64__/$helper_path_b64}"
remote_script="${remote_script/__SUDOERS_B64__/$sudoers_path_b64}"
remote_script="${remote_script/__MODE_B64__/$mode_b64}"
remote_script="${remote_script/__HELPER_PAYLOAD_B64__/$helper_payload_b64}"

log "Запуск workflow openclaw_update_permissions: mode=${MODE}, host=${OPENCLAW_HOST}, users=${BOT_UPDATE_USERS}"
run_remote_script "$OPENCLAW_HOST" "$remote_script"
log "Workflow openclaw_update_permissions завершён"
