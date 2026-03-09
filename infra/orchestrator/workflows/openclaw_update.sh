#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_NODE="${OPENCLAW_NODE:-node}"
OPENCLAW_RUNNER="${OPENCLAW_RUNNER:-scripts/run-node.mjs}"
UPDATE_CHANNEL="${UPDATE_CHANNEL:-stable}"
MODE="${1:-inspect}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/openclaw_update_${STAMP}.txt"

mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"
openclaw_dir_b64="$(printf '%s' "$OPENCLAW_DIR" | base64 | tr -d '\n')"
node_bin_b64="$(printf '%s' "$OPENCLAW_NODE" | base64 | tr -d '\n')"
runner_b64="$(printf '%s' "$OPENCLAW_RUNNER" | base64 | tr -d '\n')"
channel_b64="$(printf '%s' "$UPDATE_CHANNEL" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
openclaw_dir="$(printf '%s' '__OPENCLAW_DIR_B64__' | base64 -d)"
node_bin="$(printf '%s' '__NODE_BIN_B64__' | base64 -d)"
runner="$(printf '%s' '__RUNNER_B64__' | base64 -d)"
update_channel="$(printf '%s' '__CHANNEL_B64__' | base64 -d)"

strip_ansi() {
  sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g'
}

run_openclaw() {
  if [ -f "${openclaw_dir}/dist/entry.js" ]; then
    (cd "${openclaw_dir}" && OPENCLAW_RUNNER_LOG=0 "${node_bin}" dist/entry.js "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/${runner}" ]; then
    (cd "${openclaw_dir}" && OPENCLAW_RUNNER_LOG=0 "${node_bin}" "${runner}" "$@")
    return $?
  fi
  if command -v openclaw >/dev/null 2>&1; then
    openclaw "$@"
    return $?
  fi
  echo "ОШИБКА: не найден OpenClaw CLI (dist/entry.js, ${runner}, openclaw)" >&2
  return 1
}

update_status() {
  local raw rc
  set +e
  raw="$(run_openclaw update status 2>&1)"
  rc=$?
  set -e
  printf '%s\n' "$raw" | strip_ansi
  return $rc
}

status_has_update() {
  local status_text="$1"
  printf '%s\n' "$status_text" | grep -Eqi 'доступно обновлен|update available|новая версия|available .*update'
}

run_update_attempt() {
  local variant="$1"
  case "$variant" in
    1) run_openclaw update ;;
    2) run_openclaw update apply ;;
    3) run_openclaw update --yes ;;
    *) return 2 ;;
  esac
}

if [ ! -d "$openclaw_dir" ]; then
  echo "ОШИБКА: каталог OpenClaw не найден: $openclaw_dir" >&2
  exit 1
fi

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=$mode"
echo "openclaw_dir=$openclaw_dir"
echo "update_channel=$update_channel"
echo "openclaw_dir_owner=$(stat -c '%U:%G' "$openclaw_dir" 2>/dev/null || echo unknown)"
echo "node_path=$(command -v "$node_bin" 2>/dev/null || echo missing)"

status_before="$(update_status || true)"
echo "--- openclaw_update_status_before ---"
printf '%s\n' "$status_before"

if [ "$mode" = "inspect" ]; then
  exit 0
fi

if ! status_has_update "$status_before"; then
  echo "apply_result=skip_no_update_detected"
  exit 0
fi

dirty_backup_dir=""
dirty_stash_ref=""
dirty_profile_backup=""
if [ -d "${openclaw_dir}/.git" ] && command -v git >/dev/null 2>&1; then
  git_status_before="$(git -C "${openclaw_dir}" status --porcelain 2>/dev/null || true)"
  if [ -n "${git_status_before}" ]; then
    stamp="$(date '+%Y%m%d_%H%M%S_%Z')"
    dirty_backup_dir="${openclaw_dir}/.openclaw-update-backup-${stamp}"
    mkdir -p "${dirty_backup_dir}"
    printf '%s\n' "${git_status_before}" >"${dirty_backup_dir}/git_status_before.txt"
    git -C "${openclaw_dir}" diff >"${dirty_backup_dir}/git_diff_before.patch" || true
    git -C "${openclaw_dir}" diff --cached >"${dirty_backup_dir}/git_diff_cached_before.patch" || true
    if [ -f "${openclaw_dir}/.env.security_profile" ]; then
      dirty_profile_backup="${dirty_backup_dir}/env_security_profile.backup"
      cp -a "${openclaw_dir}/.env.security_profile" "${dirty_profile_backup}"
    fi

    stash_out="$(git -C "${openclaw_dir}" stash push --include-untracked -m "openclaw-auto-update-${stamp}" 2>&1 || true)"
    echo "--- dirty_worktree_stash ---"
    printf '%s\n' "${stash_out}"
    dirty_stash_ref="$(git -C "${openclaw_dir}" stash list | head -n1 | cut -d: -f1 || true)"
    echo "dirty_backup_dir=${dirty_backup_dir}"
    echo "dirty_stash_ref=${dirty_stash_ref:-<none>}"
  fi
fi

apply_ok=0
for attempt in 1 2 3; do
  set +e
  out="$(run_update_attempt "$attempt" 2>&1)"
  rc=$?
  set -e
  echo "--- apply_attempt_${attempt}_rc=${rc} ---"
  printf '%s\n' "$out" | strip_ansi
  if [ "$rc" -eq 0 ]; then
    apply_ok=1
    break
  fi
done

if [ "$apply_ok" -ne 1 ]; then
  if [ -n "${dirty_profile_backup}" ] && [ ! -f "${openclaw_dir}/.env.security_profile" ]; then
    cp -a "${dirty_profile_backup}" "${openclaw_dir}/.env.security_profile"
  fi
  echo "ОШИБКА: все попытки обновить OpenClaw завершились ошибкой" >&2
  exit 1
fi

status_after="$(update_status || true)"
echo "--- openclaw_update_status_after ---"
printf '%s\n' "$status_after"

if status_has_update "$status_after"; then
  if [ -n "${dirty_profile_backup}" ] && [ ! -f "${openclaw_dir}/.env.security_profile" ]; then
    cp -a "${dirty_profile_backup}" "${openclaw_dir}/.env.security_profile"
  fi
  echo "ОШИБКА: после применения update статус по-прежнему сообщает о доступном обновлении" >&2
  exit 1
fi

if [ -n "${dirty_profile_backup}" ] && [ ! -f "${openclaw_dir}/.env.security_profile" ]; then
  cp -a "${dirty_profile_backup}" "${openclaw_dir}/.env.security_profile"
fi

if [ -n "${dirty_stash_ref}" ]; then
  echo "dirty_changes_saved_in_stash=${dirty_stash_ref}"
  if [ -n "${dirty_backup_dir}" ]; then
    echo "dirty_changes_backup_dir=${dirty_backup_dir}"
  fi
fi

echo "apply_result=ok"
REMOTE

remote_script="${remote_script/__MODE_B64__/$mode_b64}"
remote_script="${remote_script/__OPENCLAW_DIR_B64__/$openclaw_dir_b64}"
remote_script="${remote_script/__NODE_BIN_B64__/$node_bin_b64}"
remote_script="${remote_script/__RUNNER_B64__/$runner_b64}"
remote_script="${remote_script/__CHANNEL_B64__/$channel_b64}"

log "Запуск workflow openclaw_update: mode=${MODE}, host=${OPENCLAW_HOST}, channel=${UPDATE_CHANNEL}"
{
  echo "# OpenClaw Update"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${OPENCLAW_HOST}"
  echo "Режим: ${MODE}"
  echo "Канал: ${UPDATE_CHANNEL}"
  echo
  run_remote_script "$OPENCLAW_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "Workflow openclaw_update завершён"
log "Отчет: ${REPORT_FILE}"
