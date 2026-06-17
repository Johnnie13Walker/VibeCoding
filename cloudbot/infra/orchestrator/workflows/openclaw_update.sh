#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_NODE="${OPENCLAW_NODE:-node}"
OPENCLAW_RUNNER="${OPENCLAW_RUNNER:-scripts/run-node.mjs}"
OPENCLAW_COMPILE_CACHE_DIR="${OPENCLAW_COMPILE_CACHE_DIR:-/var/tmp/openclaw-compile-cache}"
OPENCLAW_NO_RESPAWN="${OPENCLAW_NO_RESPAWN:-1}"
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
compile_cache_b64="$(printf '%s' "$OPENCLAW_COMPILE_CACHE_DIR" | base64 | tr -d '\n')"
no_respawn_b64="$(printf '%s' "$OPENCLAW_NO_RESPAWN" | base64 | tr -d '\n')"
channel_b64="$(printf '%s' "$UPDATE_CHANNEL" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
openclaw_dir="$(printf '%s' '__OPENCLAW_DIR_B64__' | base64 -d)"
node_bin="$(printf '%s' '__NODE_BIN_B64__' | base64 -d)"
runner="$(printf '%s' '__RUNNER_B64__' | base64 -d)"
compile_cache_dir="$(printf '%s' '__COMPILE_CACHE_B64__' | base64 -d)"
no_respawn="$(printf '%s' '__NO_RESPAWN_B64__' | base64 -d)"
update_channel="$(printf '%s' '__CHANNEL_B64__' | base64 -d)"
update_backup_root="${UPDATE_BACKUP_ROOT:-/var/backups/openclaw/update}"

strip_ansi() {
  sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g'
}

run_openclaw() {
  mkdir -p "${compile_cache_dir}"
  if command -v openclaw >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 openclaw "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/dist/entry.js" ]; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 "${node_bin}" dist/entry.js "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/${runner}" ]; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 "${node_bin}" "${runner}" "$@")
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

restore_backed_up_untracked() {
  local manifest rel src dst
  [ -n "${dirty_backup_dir:-}" ] || return 0
  [ -n "${dirty_untracked_dir:-}" ] || return 0
  manifest="${dirty_backup_dir}/untracked_paths.txt"
  [ -f "$manifest" ] || return 0

  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    src="${dirty_untracked_dir}/${rel}"
    dst="${openclaw_dir}/${rel}"
    [ -e "$src" ] || [ -L "$src" ] || continue
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      continue
    fi
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    echo "restored_untracked=${rel}"
  done <"$manifest"
}

print_runtime_search_state() {
  local cfg="${OPENCLAW_CONFIG_PATH:-/root/.openclaw/openclaw.json}"
  local provider="" base_url="" engine="" image_pin=""

  echo "--- runtime_search_state ---"
  echo "search_config_path=${cfg}"
  if [ ! -f "$cfg" ]; then
    echo "search_config_state=missing"
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "search_config_state=jq_missing"
    return 0
  fi

  provider="$(jq -r '.tools.web.search.provider // empty' "$cfg" 2>/dev/null || true)"
  base_url="$(jq -r '.tools.web.search.duckduckgo.baseUrl // empty' "$cfg" 2>/dev/null || true)"
  engine="$(jq -r '.tools.web.search.duckduckgo.engine // empty' "$cfg" 2>/dev/null || true)"

  echo "search_provider=${provider:-<empty>}"
  echo "search_duckduckgo_base_url=${base_url:-<empty>}"
  echo "search_duckduckgo_engine=${engine:-<empty>}"

  if [ -f "${openclaw_dir}/.env" ]; then
    image_pin="$(sed -n 's/^OPENCLAW_IMAGE=//p' "${openclaw_dir}/.env" | tail -n1)"
    echo "openclaw_image=${image_pin:-<empty>}"
  else
    echo "openclaw_image=<env_missing>"
  fi
}

verify_duckduckgo_runtime_after_update() {
  local cfg="${OPENCLAW_CONFIG_PATH:-/root/.openclaw/openclaw.json}"
  local provider="" base_url="" engine="" probe_output="" compose_output="" container_name=""

  echo "--- duckduckgo_runtime_verify ---"
  if [ ! -f "$cfg" ]; then
    echo "duckduckgo_runtime_verify=skip reason=missing_config"
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "duckduckgo_runtime_verify=skip reason=jq_missing"
    return 0
  fi

  provider="$(jq -r '.tools.web.search.provider // empty' "$cfg" 2>/dev/null || true)"
  base_url="$(jq -r '.tools.web.search.duckduckgo.baseUrl // empty' "$cfg" 2>/dev/null || true)"
  engine="$(jq -r '.tools.web.search.duckduckgo.engine // empty' "$cfg" 2>/dev/null || true)"

  if [ "${provider:-}" != "duckduckgo" ]; then
    echo "duckduckgo_runtime_verify=skip reason=provider_${provider:-missing}"
    return 0
  fi
  if [ -z "${base_url:-}" ]; then
    echo "duckduckgo_runtime_verify=skip reason=no_searxng_base_url"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "duckduckgo_runtime_verify=skip reason=docker_compose_missing"
    return 0
  fi
  if [ ! -f "${openclaw_dir}/docker-compose.yml" ] && [ ! -f "${openclaw_dir}/docker-compose.yaml" ]; then
    echo "duckduckgo_runtime_verify=skip reason=compose_file_missing"
    return 0
  fi

  set +e
  compose_output="$(cd "${openclaw_dir}" && docker compose ps 2>&1)"
  rc=$?
  set -e
  echo "--- docker_compose_ps_after_update ---"
  printf '%s\n' "${compose_output}"
  if [ "$rc" -ne 0 ]; then
    echo "ОШИБКА: не удалось проверить docker compose состояние после update" >&2
    return 1
  fi

  container_name="$(cd "${openclaw_dir}" && docker compose ps -q openclaw-gateway 2>/dev/null | head -n1 || true)"
  if [ -z "${container_name:-}" ]; then
    container_name="$(docker ps --format '{{.ID}} {{.Names}}' | awk '/openclaw-gateway/ { print $1; exit }' || true)"
  fi
  if [ -z "${container_name:-}" ]; then
    echo "duckduckgo_runtime_verify=skip reason=gateway_container_not_found"
    return 0
  fi

  set +e
  probe_output="$(
    docker exec \
      -e SEARCH_BASE_URL="${base_url}" \
      -e SEARCH_ENGINE="${engine:-duckduckgo}" \
      "${container_name}" \
      sh -lc 'node - <<'"'"'NODE'"'"'
const baseUrl = (process.env.SEARCH_BASE_URL || "").replace(/\/+$/, "");
const engine = process.env.SEARCH_ENGINE || "duckduckgo";
const url = `${baseUrl}/search?q=openai&format=json&engines=${encodeURIComponent(engine)}&pageno=1&language=ru&safesearch=0&categories=general`;

async function main() {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const payload = await response.json().catch(() => ({}));
  const count = Array.isArray(payload.results) ? payload.results.length : 0;
  console.log(`status=${response.status}`);
  console.log(`result_count=${count}`);
  if (!response.ok) process.exit(2);
  if (!Array.isArray(payload.results)) process.exit(3);
}

main().catch((error) => {
  console.error(String(error && error.message || error));
  process.exit(1);
});
NODE' 2>&1
  )"
  rc=$?
  set -e

  echo "--- duckduckgo_probe_after_update ---"
  printf '%s\n' "${probe_output}"
  if [ "$rc" -ne 0 ]; then
    echo "ОШИБКА: DuckDuckGo -> SearXNG probe не прошёл после update" >&2
    return 1
  fi

  echo "duckduckgo_runtime_verify=ok"
  return 0
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
print_runtime_search_state

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
dirty_untracked_dir=""
if [ -d "${openclaw_dir}/.git" ] && command -v git >/dev/null 2>&1; then
  git_status_before="$(git -C "${openclaw_dir}" status --porcelain 2>/dev/null || true)"
  if [ -n "${git_status_before}" ]; then
    tracked_paths="$(printf '%s\n' "${git_status_before}" | awk 'substr($0,1,2)!="??"{print substr($0,4)}')"
    unexpected_tracked_paths="$(printf '%s\n' "${tracked_paths}" | while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      case "$rel" in
        docker-compose.yml) ;;
        *) printf '%s\n' "$rel" ;;
      esac
    done)"
    if [ -n "${unexpected_tracked_paths}" ]; then
      echo "ОШИБКА: обнаружены tracked-изменения, которые workflow не умеет безопасно восстанавливать после update:" >&2
      printf '%s\n' "${unexpected_tracked_paths}" >&2
      exit 1
    fi

    stamp="$(date '+%Y%m%d_%H%M%S_%Z')"
    dirty_backup_dir="${update_backup_root}/openclaw-update-${stamp}"
    dirty_untracked_dir="${dirty_backup_dir}/untracked_restore"
    mkdir -p "${dirty_backup_dir}"
    printf '%s\n' "${git_status_before}" >"${dirty_backup_dir}/git_status_before.txt"
    git -C "${openclaw_dir}" diff >"${dirty_backup_dir}/git_diff_before.patch" || true
    git -C "${openclaw_dir}" diff --cached >"${dirty_backup_dir}/git_diff_cached_before.patch" || true
    if [ -f "${openclaw_dir}/.env.security_profile" ]; then
      dirty_profile_backup="${dirty_backup_dir}/env_security_profile.backup"
      cp -a "${openclaw_dir}/.env.security_profile" "${dirty_profile_backup}"
    fi
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      src="${openclaw_dir}/${rel}"
      dst="${dirty_untracked_dir}/${rel}"
      [ -e "$src" ] || [ -L "$src" ] || continue
      mkdir -p "$(dirname "$dst")"
      cp -a "$src" "$dst"
      printf '%s\n' "$rel" >>"${dirty_backup_dir}/untracked_paths.txt"
    done < <(printf '%s\n' "${git_status_before}" | awk 'substr($0,1,2)=="??"{print substr($0,4)}')

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
  restore_backed_up_untracked
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
  restore_backed_up_untracked
  echo "ОШИБКА: после применения update статус по-прежнему сообщает о доступном обновлении" >&2
  exit 1
fi

if ! verify_duckduckgo_runtime_after_update; then
  if [ -n "${dirty_profile_backup}" ] && [ ! -f "${openclaw_dir}/.env.security_profile" ]; then
    cp -a "${dirty_profile_backup}" "${openclaw_dir}/.env.security_profile"
  fi
  restore_backed_up_untracked
  exit 1
fi

if [ -n "${dirty_profile_backup}" ] && [ ! -f "${openclaw_dir}/.env.security_profile" ]; then
  cp -a "${dirty_profile_backup}" "${openclaw_dir}/.env.security_profile"
fi
restore_backed_up_untracked

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
remote_script="${remote_script/__COMPILE_CACHE_B64__/$compile_cache_b64}"
remote_script="${remote_script/__NO_RESPAWN_B64__/$no_respawn_b64}"
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
