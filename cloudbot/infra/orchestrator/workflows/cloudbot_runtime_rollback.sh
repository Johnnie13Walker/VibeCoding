#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

TARGET_HOST="${LARISA_RUNTIME_HOST:-${CLOUDBOT_RUNTIME_HOST:-${PRIMARY_HOST:-}}}"
RUNTIME_ROOT="${LARISA_RUNTIME_ROOT:-${CLOUDBOT_RUNTIME_ROOT:-/opt/cloudbot-runtime/larisa}}"
CURRENT_LINK="${LARISA_RUNTIME_CURRENT_LINK:-${CLOUDBOT_RUNTIME_CURRENT_LINK:-$RUNTIME_ROOT/current}}"
REMOTE_LOCK_PATH="${LARISA_RUNTIME_LOCK_PATH:-${CLOUDBOT_RUNTIME_LOCK_PATH:-$RUNTIME_ROOT/.deploy.lock}}"
MODE="${1:-inspect}"
TARGET_RELEASE="${2:-${TARGET_RELEASE:-}}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_runtime_rollback_${STAMP}.txt"
LOCK_OWNER="cloudbot_runtime_rollback:${MODE}:${TARGET_RELEASE:-none}:$(hostname):$$"
LOCK_HELD=0

require_env TARGET_HOST SSH_USER SSH_KEY_PATH SSH_PORT
mkdir -p "$REPORT_DIR"

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

if [[ "$MODE" == "apply" ]] && [[ -z "$TARGET_RELEASE" ]]; then
  fail "Для apply нужно явно указать target release вторым аргументом."
fi

cleanup_remote_lock() {
  local exit_code=$?
  if [[ "$LOCK_HELD" == "1" ]]; then
    release_remote_lock "$TARGET_HOST" "$REMOTE_LOCK_PATH" || true
  fi
  return "$exit_code"
}

if [[ "$MODE" == "apply" ]]; then
  trap cleanup_remote_lock EXIT
  acquire_remote_lock "$TARGET_HOST" "$REMOTE_LOCK_PATH" "$LOCK_OWNER"
  LOCK_HELD=1
fi

printf -v runtime_root_q '%q' "$RUNTIME_ROOT"
printf -v current_link_q '%q' "$CURRENT_LINK"
printf -v target_release_q '%q' "$TARGET_RELEASE"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

runtime_root=__RUNTIME_ROOT_Q__
current_link=__CURRENT_LINK_Q__
target_release=__TARGET_RELEASE_Q__
releases_dir="${runtime_root}/releases"

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "runtime_root=${runtime_root}"
echo "current_link=${current_link}"
echo "target_release=${target_release:-<not-set>}"

if [[ ! -d "${releases_dir}" ]]; then
  echo "ERROR: releases directory не найден: ${releases_dir}" >&2
  exit 1
fi

current_target="$(readlink -f "${current_link}" 2>/dev/null || true)"
current_release=""
if [[ -n "${current_target}" ]]; then
  current_release="$(basename "${current_target}")"
fi

echo "current_target=${current_target:-<missing>}"
echo "current_release=${current_release:-<missing>}"
echo "available_releases_begin"
shopt -s nullglob
release_paths=("${releases_dir}"/*)
if [[ "${#release_paths[@]}" -eq 0 ]]; then
  echo "<none>"
else
  ls -1dt "${release_paths[@]}" | while IFS= read -r path; do
    release_name="$(basename "${path}")"
    release_commit=""
    if [[ -f "${path}/RELEASE_COMMIT" ]]; then
      release_commit="$(cat "${path}/RELEASE_COMMIT")"
    fi
    marker=""
    if [[ "${path}" == "${current_target}" ]]; then
      marker=" current"
    fi
    printf '%s%s %s\n' "${release_name}" "${marker}" "${release_commit:-<missing-commit>}"
  done
fi
echo "available_releases_end"

if [[ -z "${target_release}" ]]; then
  exit 0
fi

target_dir="${releases_dir}/${target_release}"
if [[ ! -d "${target_dir}" ]]; then
  echo "ERROR: release не найден: ${target_dir}" >&2
  exit 1
fi
if [[ ! -f "${target_dir}/RELEASE_COMMIT" ]]; then
  echo "ERROR: в release отсутствует RELEASE_COMMIT: ${target_dir}" >&2
  exit 1
fi

target_commit="$(cat "${target_dir}/RELEASE_COMMIT")"
target_branch=""
target_id=""
if [[ -f "${target_dir}/RELEASE_BRANCH" ]]; then
  target_branch="$(cat "${target_dir}/RELEASE_BRANCH")"
fi
if [[ -f "${target_dir}/RELEASE_ID" ]]; then
  target_id="$(cat "${target_dir}/RELEASE_ID")"
fi

echo "target_dir=${target_dir}"
echo "target_commit=${target_commit}"
echo "target_branch=${target_branch:-<missing>}"
echo "target_id=${target_id:-<missing>}"

if [[ "${current_target}" == "${target_dir}" ]]; then
  echo "rollback=skipped_already_current"
  exit 0
fi

ln -sfn "${target_dir}" "${current_link}"
new_target="$(readlink -f "${current_link}")"
if [[ "${new_target}" != "${target_dir}" ]]; then
  echo "ERROR: current не перепривязан на target release" >&2
  exit 1
fi
if [[ ! -f "${current_link}/RELEASE_COMMIT" ]]; then
  echo "ERROR: после rollback отсутствует RELEASE_COMMIT в current" >&2
  exit 1
fi

echo "rollback=applied"
echo "new_target=${new_target}"
echo "new_release_commit=$(cat "${current_link}/RELEASE_COMMIT")"
if [[ -f "${current_link}/RELEASE_BRANCH" ]]; then
  echo "new_release_branch=$(cat "${current_link}/RELEASE_BRANCH")"
fi
if [[ -f "${current_link}/RELEASE_ID" ]]; then
  echo "new_release_id=$(cat "${current_link}/RELEASE_ID")"
fi
REMOTE

remote_script="${remote_script/__RUNTIME_ROOT_Q__/$runtime_root_q}"
remote_script="${remote_script/__CURRENT_LINK_Q__/$current_link_q}"
remote_script="${remote_script/__TARGET_RELEASE_Q__/$target_release_q}"

log "cloudbot_runtime_rollback: старт (mode=${MODE}, host=${TARGET_HOST}, target_release=${TARGET_RELEASE:-<not-set>})"

{
  echo "# Cloudbot Runtime Rollback"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${TARGET_HOST}"
  echo "Режим: ${MODE}"
  echo "Runtime root: ${RUNTIME_ROOT}"
  echo "Current link: ${CURRENT_LINK}"
  echo "Remote lock: ${REMOTE_LOCK_PATH}"
  echo "Target release: ${TARGET_RELEASE:-<not-set>}"
  if [[ "$MODE" == "apply" ]]; then
    echo "Lock owner: ${LOCK_OWNER}"
  fi
  echo
  run_remote_script "$TARGET_HOST" "$remote_script"
} | tee "$REPORT_FILE"

if [[ "$MODE" == "apply" ]]; then
  release_remote_lock "$TARGET_HOST" "$REMOTE_LOCK_PATH"
  LOCK_HELD=0
  trap - EXIT
fi

log "cloudbot_runtime_rollback: завершен, отчет=${REPORT_FILE}"
