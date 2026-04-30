#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
MODE="${1:-inspect}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
OPENCLAW_BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-18790}"
OPENCLAW_COMPILE_CACHE_DIR="${OPENCLAW_COMPILE_CACHE_DIR:-/var/tmp/openclaw-compile-cache}"
OPENCLAW_NO_RESPAWN="${OPENCLAW_NO_RESPAWN:-1}"
OPENCLAW_ENV_FILE="${OPENCLAW_ENV_FILE:-/opt/openclaw/.env}"
LOCKDOWN_GATEWAY_BIND="${LOCKDOWN_GATEWAY_BIND:-1}"
OPENCLAW_CONFIG_PATHS="${OPENCLAW_CONFIG_PATHS:-/root/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json /home/ops/.openclaw/openclaw.json}"
OPENCLAW_SANDBOX_MODE_TARGET="${OPENCLAW_SANDBOX_MODE_TARGET:-off}"
AUTO_DISABLE_SANDBOX_WITHOUT_DOCKER="${AUTO_DISABLE_SANDBOX_WITHOUT_DOCKER:-1}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/openclaw_gateway_repair_${STAMP}.txt"
mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"
openclaw_dir_b64="$(printf '%s' "$OPENCLAW_DIR" | base64 | tr -d '\n')"
gateway_port_b64="$(printf '%s' "$OPENCLAW_GATEWAY_PORT" | base64 | tr -d '\n')"
bridge_port_b64="$(printf '%s' "$OPENCLAW_BRIDGE_PORT" | base64 | tr -d '\n')"
compile_cache_b64="$(printf '%s' "$OPENCLAW_COMPILE_CACHE_DIR" | base64 | tr -d '\n')"
no_respawn_b64="$(printf '%s' "$OPENCLAW_NO_RESPAWN" | base64 | tr -d '\n')"
env_file_b64="$(printf '%s' "$OPENCLAW_ENV_FILE" | base64 | tr -d '\n')"
lockdown_b64="$(printf '%s' "$LOCKDOWN_GATEWAY_BIND" | base64 | tr -d '\n')"
config_paths_b64="$(printf '%s' "$OPENCLAW_CONFIG_PATHS" | base64 | tr -d '\n')"
sandbox_mode_target_b64="$(printf '%s' "$OPENCLAW_SANDBOX_MODE_TARGET" | base64 | tr -d '\n')"
auto_disable_sandbox_b64="$(printf '%s' "$AUTO_DISABLE_SANDBOX_WITHOUT_DOCKER" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
openclaw_dir="$(printf '%s' '__OPENCLAW_DIR_B64__' | base64 -d)"
gateway_port="$(printf '%s' '__OPENCLAW_GATEWAY_PORT_B64__' | base64 -d)"
bridge_port="$(printf '%s' '__OPENCLAW_BRIDGE_PORT_B64__' | base64 -d)"
compile_cache_dir="$(printf '%s' '__OPENCLAW_COMPILE_CACHE_B64__' | base64 -d)"
no_respawn="$(printf '%s' '__OPENCLAW_NO_RESPAWN_B64__' | base64 -d)"
env_file="$(printf '%s' '__OPENCLAW_ENV_FILE_B64__' | base64 -d)"
lockdown_gateway_bind="$(printf '%s' '__LOCKDOWN_GATEWAY_BIND_B64__' | base64 -d)"
config_paths_raw="$(printf '%s' '__CONFIG_PATHS_B64__' | base64 -d)"
sandbox_mode_target="$(printf '%s' '__SANDBOX_MODE_TARGET_B64__' | base64 -d)"
auto_disable_sandbox_without_docker="$(printf '%s' '__AUTO_DISABLE_SANDBOX_B64__' | base64 -d)"
compose_file="${openclaw_dir}/docker-compose.yml"
compose_backup=""
compose_updated="0"
docker_present="0"
jq_present="0"
container_names_file="/tmp/openclaw_docker_names.txt"

IFS=' ' read -r -a cfg_files <<< "${config_paths_raw}"

run_openclaw() {
  mkdir -p "${compile_cache_dir}"
  if command -v openclaw >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 openclaw "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/dist/entry.js" ] && command -v node >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 node dist/entry.js "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/scripts/run-node.mjs" ] && command -v node >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && NODE_COMPILE_CACHE="${compile_cache_dir}" OPENCLAW_NO_RESPAWN="${no_respawn}" OPENCLAW_RUNNER_LOG=0 node scripts/run-node.mjs "$@")
    return $?
  fi
  echo "ОШИБКА: OpenClaw CLI не найден" >&2
  return 127
}

print_cmd() {
  local title="$1"
  shift
  echo "--- ${title} ---"
  set +e
  "$@"
  local rc=$?
  set -e
  echo "rc=${rc}"
}

print_compose_ports() {
  if [ -f "$compose_file" ]; then
    awk '
      /openclaw-gateway:/ {in_service=1}
      in_service && /^[^[:space:]]/ && $0 !~ /openclaw-gateway:/ {in_service=0}
      in_service && /ports:/ {in_ports=1; next}
      in_ports && /^[[:space:]]+-/ {print}
      in_ports && !/^[[:space:]]+-/ {in_ports=0}
    ' "$compose_file"
  else
    echo "missing $compose_file"
  fi
}

print_startup_env_state() {
  echo "--- startup_env_file ---"
  if [ -f "$env_file" ]; then
    grep -E '^(NODE_COMPILE_CACHE|OPENCLAW_NO_RESPAWN)=' "$env_file" || echo "startup_env_keys=missing"
  else
    echo "missing $env_file"
  fi
  echo "--- startup_env_compose ---"
  if [ -f "$compose_file" ]; then
    sed -n '/openclaw-gateway:/,/openclaw-cli:/p' "$compose_file" | grep -E 'NODE_COMPILE_CACHE|OPENCLAW_NO_RESPAWN' || echo "startup_compose_keys=missing"
  else
    echo "missing $compose_file"
  fi
}

apply_startup_env_file() {
  local tmp changed="0" backup=""
  install -d -m 700 "$(dirname "$env_file")"
  [ -f "$env_file" ] || touch "$env_file"
  chmod 600 "$env_file" || true
  tmp="$(mktemp)"
  cp -a "$env_file" "$tmp"
  if ! grep -q '^NODE_COMPILE_CACHE=' "$tmp"; then
    printf 'NODE_COMPILE_CACHE=%s\n' "$compile_cache_dir" >>"$tmp"
    changed="1"
  fi
  if ! grep -q '^OPENCLAW_NO_RESPAWN=' "$tmp"; then
    printf 'OPENCLAW_NO_RESPAWN=%s\n' "$no_respawn" >>"$tmp"
    changed="1"
  fi
  if [ "$changed" != "1" ]; then
    rm -f "$tmp"
    echo "startup_env_file_update=skip reason=already_present"
    return 10
  fi
  backup="${env_file}.bak.$(date '+%Y%m%d_%H%M%S_MSK')"
  cp -a "$env_file" "$backup" 2>/dev/null || true
  mv "$tmp" "$env_file"
  chmod 600 "$env_file" || true
  echo "startup_env_file_update=applied"
  echo "startup_env_file_backup=${backup}"
  return 0
}

apply_compose_startup_env() {
  local tmp_file
  tmp_file="$(mktemp)"
  cp -a "$compose_file" "$tmp_file"
  python3 - "$tmp_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
needle = "      TERM: xterm-256color\n"
replacement = needle + "      NODE_COMPILE_CACHE: ${NODE_COMPILE_CACHE:-/var/tmp/openclaw-compile-cache}\n" + "      OPENCLAW_NO_RESPAWN: ${OPENCLAW_NO_RESPAWN:-1}\n"
parts = text.split(needle)
if len(parts) <= 1:
    sys.exit(0)
result = [parts[0]]
insertions = 0
for part in parts[1:]:
    prefix = part.split("volumes:", 1)[0]
    if "NODE_COMPILE_CACHE:" in prefix or "OPENCLAW_NO_RESPAWN:" in prefix:
        result.append(needle)
    else:
        result.append(replacement)
        insertions += 1
    result.append(part)
path.write_text("".join(result))
print(insertions)
PY
  if cmp -s "$compose_file" "$tmp_file"; then
    rm -f "$tmp_file"
    echo "startup_compose_update=skip reason=already_present"
    return 10
  fi
  compose_backup="${compose_file}.bak.$(date '+%Y%m%d_%H%M%S_MSK')"
  cp -a "$compose_file" "$compose_backup"
  mv "$tmp_file" "$compose_file"
  compose_updated="1"
  echo "startup_compose_update=applied"
  return 0
}

apply_compose_loopback_publish() {
  local tmp_file gateway_pattern bridge_pattern
  tmp_file="$(mktemp)"
  gateway_pattern="- \"\${OPENCLAW_GATEWAY_PORT:-${gateway_port}}:18789\""
  bridge_pattern="- \"\${OPENCLAW_BRIDGE_PORT:-${bridge_port}}:18790\""

  cp -a "$compose_file" "$tmp_file"
  sed -i \
    -e "s#${gateway_pattern}#- \"127.0.0.1:\${OPENCLAW_GATEWAY_PORT:-${gateway_port}}:18789\"#" \
    -e "s#${bridge_pattern}#- \"127.0.0.1:\${OPENCLAW_BRIDGE_PORT:-${bridge_port}}:18790\"#" \
    "$tmp_file"

  if cmp -s "$compose_file" "$tmp_file"; then
    rm -f "$tmp_file"
    return 1
  fi

  compose_backup="${compose_file}.bak.$(date '+%Y%m%d_%H%M%S_MSK')"
  cp -a "$compose_file" "$compose_backup"
  mv "$tmp_file" "$compose_file"
  compose_updated="1"
  return 0
}

docker_compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return $?
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return $?
  fi
  echo "ОШИБКА: docker compose не найден" >&2
  return 127
}

restart_openclaw_runtime() {
  local restart_rc="1"
  local restarted="0"

  echo "--- openclaw_runtime_restart ---"
  if [ "$docker_present" = "1" ] && [ -s "$container_names_file" ]; then
    while IFS= read -r container_name; do
      [ -n "$container_name" ] || continue
      docker restart "$container_name" >/dev/null
      echo "docker_restart_container=${container_name}"
      restarted="1"
    done < "$container_names_file"
    if [ "$restarted" = "1" ]; then
      echo "openclaw_runtime_restart=container_restart"
      sleep 5
      return 0
    fi
  fi

  set +e
  run_openclaw gateway restart
  restart_rc=$?
  set -e
  echo "openclaw_gateway_restart_rc=${restart_rc}"
  if [ "$restart_rc" = "0" ]; then
    restarted="1"
  fi

  if [ "$restarted" != "1" ]; then
    echo "openclaw_runtime_restart=skip reason=no_restart_path"
    return 1
  fi

  return 0
}

print_config_state() {
  local f="$1"
  if [ -f "$f" ]; then
    stat -c '%a %U:%G %n' "$f"
    if [ -d "$(dirname "$f")" ]; then
      stat -c '%a %U:%G %n' "$(dirname "$f")"
    fi
    if [ "$jq_present" = "1" ]; then
      local sandbox_mode search_provider search_candidate search_keys
      sandbox_mode="$(jq -r '.agents.defaults.sandbox.mode // empty' "$f" 2>/dev/null || true)"
      search_provider="$(jq -r '.tools.web.search.provider // empty' "$f" 2>/dev/null || true)"
      search_candidate="$(detect_search_provider_candidate "$f")"
      search_keys="$(jq -r '(.tools.web.search // {}) | if type == "object" then (keys_unsorted | join(",")) else "" end' "$f" 2>/dev/null || true)"
      echo "sandbox_mode=${sandbox_mode:-<empty>}"
      echo "search_provider=${search_provider:-<empty>}"
      echo "search_candidate=${search_candidate:-<none>}"
      echo "search_keys=${search_keys:-<empty>}"
    else
      echo "sandbox_mode=<jq_missing>"
    fi
  else
    echo "missing $f"
  fi
}

valid_search_provider() {
  case "${1:-}" in
    duckduckgo) return 0 ;;
    *) return 1 ;;
  esac
}

detect_search_provider_candidate() {
  local f="$1"
  if [ "$jq_present" != "1" ] || [ ! -f "$f" ]; then
    return 0
  fi
  jq -r '
    (.tools.web.search // {}) as $s
    | if ($s | type) != "object" then ""
      elif ((($s.provider // "") | tostring) as $p | ($p == "duckduckgo")) then "duckduckgo"
      elif ($s.duckduckgo != null) then "duckduckgo"
      elif ($s.kimi != null or $s.brave != null or $s.moonshot != null) then "duckduckgo"
      else ""
      end
  ' "$f" 2>/dev/null || true
}

apply_search_provider() {
  local f="$1"
  local current candidate backup tmp after

  if [ "$jq_present" != "1" ]; then
    echo "ОШИБКА: jq не найден, невозможно обновить tools.web.search.provider" >&2
    return 1
  fi

  current="$(jq -r '.tools.web.search.provider // empty' "$f" 2>/dev/null || true)"
  candidate="$(detect_search_provider_candidate "$f")"

  echo "config_file=$f"
  echo "search_provider_before=${current:-<empty>}"
  echo "search_provider_candidate=${candidate:-<none>}"

  if valid_search_provider "${current:-}"; then
    echo "search_provider_update=skip reason=already_valid"
    echo "---"
    return 10
  fi

  if [ -z "${candidate:-}" ]; then
    echo "search_provider_update=skip reason=no_candidate"
    echo "---"
    return 10
  fi

  backup="${f}.bak.$(date '+%Y%m%d_%H%M%S_MSK')"
  cp -a "$f" "$backup"
  tmp="$(mktemp)"
  jq --arg provider "$candidate" \
    '.tools = (.tools // {}) | .tools.web = (.tools.web // {}) | .tools.web.search = (.tools.web.search // {}) | .tools.web.search.provider = $provider | del(.tools.web.search.brave) | del(.tools.web.search.kimi) | del(.tools.web.search.moonshot)' \
    "$f" > "$tmp"
  jq -e . "$tmp" >/dev/null
  chmod 600 "$tmp" || true
  mv "$tmp" "$f"
  chmod 600 "$f" || true

  after="$(jq -r '.tools.web.search.provider // empty' "$f" 2>/dev/null || true)"
  echo "search_provider_after=${after:-<empty>}"
  echo "backup_file=$backup"
  echo "---"

  if [ "$after" != "$candidate" ]; then
    echo "ОШИБКА: tools.web.search.provider не обновился до ${candidate} в ${f}" >&2
    return 1
  fi

  return 0
}

apply_sandbox_mode() {
  local f="$1"
  local target_mode="$2"
  local current after backup tmp

  if [ "$jq_present" != "1" ]; then
    echo "ОШИБКА: jq не найден, невозможно обновить sandbox.mode" >&2
    return 1
  fi

  current="$(jq -r '.agents.defaults.sandbox.mode // empty' "$f" 2>/dev/null || true)"
  echo "config_file=$f"
  echo "sandbox_mode_before=${current:-<empty>}"
  if [ "${current:-}" = "$target_mode" ]; then
    echo "sandbox_update=skip reason=already_target"
    echo "---"
    return 10
  fi

  backup="${f}.bak.$(date '+%Y%m%d_%H%M%S_MSK')"
  cp -a "$f" "$backup"
  tmp="$(mktemp)"
  jq --arg mode "$target_mode" \
    '.agents = (.agents // {}) | .agents.defaults = (.agents.defaults // {}) | .agents.defaults.sandbox = (.agents.defaults.sandbox // {}) | .agents.defaults.sandbox.mode = $mode' \
    "$f" > "$tmp"
  jq -e . "$tmp" >/dev/null
  chmod 600 "$tmp" || true
  mv "$tmp" "$f"
  chmod 600 "$f" || true

  after="$(jq -r '.agents.defaults.sandbox.mode // empty' "$f" 2>/dev/null || true)"
  echo "sandbox_mode_after=${after:-<empty>}"
  echo "backup_file=$backup"
  echo "---"

  if [ "$after" != "$target_mode" ]; then
    echo "ОШИБКА: sandbox.mode не обновился до ${target_mode} в ${f}" >&2
    return 1
  fi

  return 0
}

prime_openclaw_container_list() {
  : >"$container_names_file"
  if [ "$docker_present" = "1" ]; then
    docker ps --format '{{.Names}}' | grep -E '^openclaw' >"$container_names_file" 2>/dev/null || true
  fi
}

container_has_docker() {
  local container="$1"
  docker exec "$container" sh -lc 'command -v docker >/dev/null 2>&1'
}

container_read_sandbox_mode() {
  local container="$1"
  docker exec "$container" node -e 'const fs=require("fs"); const p="/home/node/.openclaw/openclaw.json"; if (!fs.existsSync(p)) { process.stdout.write("__MISSING__"); process.exit(0); } const data=JSON.parse(fs.readFileSync(p, "utf8")); process.stdout.write(String(data?.agents?.defaults?.sandbox?.mode || ""));'
}

container_mount_source() {
  local container="$1"
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/node/.openclaw"}}{{.Source}}{{end}}{{end}}' "$container" 2>/dev/null || true
}

probe_container_watch_access() {
  local container="$1"
  set +e
  docker exec "$container" node -e 'const fs=require("fs"); const p="/home/node/.openclaw/openclaw.json"; try { const watcher=fs.watch(p, () => {}); watcher.close(); console.log("container_watch_probe=ok"); } catch (error) { console.log("container_watch_probe=error"); console.log(String((error && error.message) || error)); process.exit(21); }'
  local rc=$?
  set -e
  echo "container_watch_probe_rc=${rc}"
}

print_container_config_state() {
  local container="$1"
  local mount_source=""
  local sandbox_mode rc docker_in_container
  echo "container=${container}"
  echo "container_user=$(docker inspect -f '{{.Config.User}}' "$container" 2>/dev/null || true)"
  mount_source="$(container_mount_source "$container")"
  echo "container_mount_source=${mount_source:-<none>}"
  if container_has_docker "$container"; then
    docker_in_container="yes"
  else
    docker_in_container="no"
  fi
  echo "container_docker=${docker_in_container}"
  set +e
  docker exec "$container" sh -lc 'id; for target in /home/node/.openclaw /home/node/.openclaw/openclaw.json; do if [ -e "$target" ]; then stat -c "%a %U:%G %n" "$target"; else echo "missing $target"; fi; done'
  rc=$?
  set -e
  echo "container_stat_rc=${rc}"
  if [ -n "$mount_source" ] && [ -d "$mount_source" ]; then
    stat -c '%a %U:%G %n' "$mount_source" || true
    if [ -f "$mount_source/openclaw.json" ]; then
      stat -c '%a %U:%G %n' "$mount_source/openclaw.json" || true
    fi
  fi
  probe_container_watch_access "$container"

  set +e
  sandbox_mode="$(container_read_sandbox_mode "$container" 2>/tmp/openclaw_container_sandbox.err)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "container_sandbox_mode=<error>"
    sed -n '1,40p' /tmp/openclaw_container_sandbox.err || true
    return 0
  fi
  if [ "$sandbox_mode" = "__MISSING__" ]; then
    echo "container_config=/home/node/.openclaw/openclaw.json missing"
  else
    echo "container_sandbox_mode=${sandbox_mode:-<empty>}"
  fi
}

apply_container_sandbox_mode() {
  local container="$1"
  local target_mode="$2"
  local current rc stamp

  set +e
  current="$(container_read_sandbox_mode "$container" 2>/tmp/openclaw_container_sandbox_apply.err)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    sed -n '1,40p' /tmp/openclaw_container_sandbox_apply.err || true
    return "$rc"
  fi

  echo "container=${container}"
  echo "container_sandbox_mode_before=${current:-<empty>}"
  if [ "$current" = "__MISSING__" ]; then
    echo "container_sandbox_update=skip reason=config_missing"
    echo "---"
    return 10
  fi
  if [ "${current:-}" = "$target_mode" ]; then
    echo "container_sandbox_update=skip reason=already_target"
    echo "---"
    return 10
  fi

  stamp="$(date '+%Y%m%d_%H%M%S_MSK')"
  docker exec -u 0 "$container" node -e 'const fs=require("fs"); const p="/home/node/.openclaw/openclaw.json"; const target=process.argv[1]; const stamp=process.argv[2]; if (!fs.existsSync(p)) { console.error(`missing ${p}`); process.exit(11); } const data=JSON.parse(fs.readFileSync(p, "utf8")); data.agents ??= {}; data.agents.defaults ??= {}; data.agents.defaults.sandbox ??= {}; const backup=`${p}.bak.${stamp}`; fs.copyFileSync(p, backup); data.agents.defaults.sandbox.mode = target; fs.writeFileSync(p, JSON.stringify(data, null, 2) + "\n"); console.log(`backup_file=${backup}`); console.log(`container_sandbox_mode_after=${data.agents.defaults.sandbox.mode}`);' "$target_mode" "$stamp"
  docker exec -u 0 "$container" sh -lc 'target="/home/node/.openclaw/openclaw.json"; [ -f "$target" ] && chmod 600 "$target" && chown 1000:1000 "$target"'
  echo "---"
  return 0
}

if command -v docker >/dev/null 2>&1; then
  docker_present="1"
fi
if command -v jq >/dev/null 2>&1; then
  jq_present="1"
fi
prime_openclaw_container_list

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=${mode}"
echo "openclaw_dir=${openclaw_dir}"
echo "lockdown_gateway_bind=${lockdown_gateway_bind}"
echo "docker_present=${docker_present}"
echo "jq_present=${jq_present}"
echo "sandbox_mode_target=${sandbox_mode_target}"
echo "auto_disable_sandbox_without_docker=${auto_disable_sandbox_without_docker}"
echo "compile_cache_dir=${compile_cache_dir}"
echo "no_respawn=${no_respawn}"

echo "--- runtime_probe ---"
if pgrep -af 'openclaw|dist/entry.js|run-node.mjs' >/tmp/openclaw_ps.txt 2>/dev/null; then
  cat /tmp/openclaw_ps.txt
else
  echo "openclaw_processes=none"
fi

if command -v systemctl >/dev/null 2>&1; then
  echo "systemctl_present=1"
  if systemctl --user is-system-running >/dev/null 2>&1; then
    echo "systemd_user_services=available"
  else
    echo "systemd_user_services=unavailable"
  fi
else
  echo "systemctl_present=0"
  echo "systemd_user_services=unavailable"
fi

echo "--- docker_runtime ---"
if [ "$docker_present" = "1" ]; then
  docker --version || true
else
  echo "docker=missing"
fi

print_cmd "openclaw_status" run_openclaw status
print_cmd "openclaw_gateway_status" run_openclaw gateway status
print_cmd "openclaw_doctor_non_interactive" run_openclaw doctor --non-interactive
echo "--- compose_ports_before ---"
print_compose_ports
print_startup_env_state
echo "--- listener_before ---"
ss -ltnp 2>/dev/null | grep -E "(:${gateway_port}|:${bridge_port})" || true

echo "--- config_permissions_before ---"
for f in "${cfg_files[@]}"; do
  print_config_state "$f"
done

echo "--- container_config_before ---"
if [ -s "$container_names_file" ]; then
  while IFS= read -r container_name; do
    [ -n "$container_name" ] || continue
    print_container_config_state "$container_name"
  done < "$container_names_file"
else
  echo "openclaw_containers=none"
fi

echo "--- sandbox_runtime_probe ---"
if [ "$docker_present" != "1" ]; then
  if [ "$jq_present" = "1" ]; then
    sandbox_runtime_risk="0"
    for f in "${cfg_files[@]}"; do
      if [ -f "$f" ]; then
        sandbox_mode="$(jq -r '.agents.defaults.sandbox.mode // empty' "$f" 2>/dev/null || true)"
        echo "config=${f} sandbox_mode=${sandbox_mode:-<empty>} docker_present=0"
        if [ "${sandbox_mode:-}" != "off" ]; then
          sandbox_runtime_risk="1"
        fi
      fi
    done
    echo "sandbox_runtime_risk=${sandbox_runtime_risk}"
  else
    echo "sandbox_runtime_risk=unknown reason=jq_missing"
  fi
else
  sandbox_runtime_risk="0"
  if [ -s "$container_names_file" ]; then
    while IFS= read -r container_name; do
      [ -n "$container_name" ] || continue
      if container_has_docker "$container_name"; then
        echo "container=${container_name} runtime_docker=present"
        continue
      fi
      set +e
      sandbox_mode="$(container_read_sandbox_mode "$container_name" 2>/tmp/openclaw_container_sandbox_probe.err)"
      rc=$?
      set -e
      if [ "$rc" -ne 0 ]; then
        echo "container=${container_name} runtime_docker=missing sandbox_probe=error"
        sed -n '1,20p' /tmp/openclaw_container_sandbox_probe.err || true
        sandbox_runtime_risk="1"
        continue
      fi
      echo "container=${container_name} runtime_docker=missing container_sandbox_mode=${sandbox_mode:-<empty>}"
      if [ "$sandbox_mode" != "__MISSING__" ] && [ "${sandbox_mode:-}" != "off" ]; then
        sandbox_runtime_risk="1"
      fi
    done < "$container_names_file"
  fi
  echo "sandbox_runtime_risk=${sandbox_runtime_risk}"
fi

echo "--- logs_last_24h ---"
if command -v journalctl >/dev/null 2>&1; then
  journalctl --since '24 hours ago' --no-pager 2>/tmp/journal_all.err \
    -u openclaw-gateway.service -u openclaw.service | tail -n 120 || true
fi
if command -v docker >/dev/null 2>&1; then
  docker ps --format '{{.Names}}' | grep -E '^openclaw' >/tmp/openclaw_docker_names.txt 2>/dev/null || true
  while IFS= read -r container_name; do
    [ -n "$container_name" ] || continue
    echo "docker_logs_container=${container_name}"
    docker logs --since 24h "$container_name" 2>&1 | tail -n 120 || true
  done </tmp/openclaw_docker_names.txt
fi

if [ "$mode" = "apply" ]; then
  sandbox_fix_applied="0"
  sandbox_restart_required="0"
  search_provider_fix_applied="0"
  search_provider_restart_required="0"
  patch_host_configs="0"
  print_cmd "openclaw_doctor_repair" run_openclaw doctor --repair
  if [ "$lockdown_gateway_bind" = "1" ] && [ -f "$compose_file" ]; then
    echo "--- compose_lockdown_apply ---"
    if apply_compose_loopback_publish; then
      echo "compose_backup=${compose_backup}"
      (cd "$openclaw_dir" && docker_compose_cmd up -d openclaw-gateway openclaw-cli)
      sleep 5
    else
      echo "compose_update=skip_already_locked_down_or_pattern_not_found"
    fi
  fi
  echo "--- startup_env_apply ---"
  if apply_startup_env_file; then
    startup_env_restart_required="1"
  else
    rc=$?
    if [ "$rc" -ne 10 ]; then
      exit "$rc"
    fi
  fi
  echo "--- startup_compose_apply ---"
  if [ -f "$compose_file" ]; then
    if apply_compose_startup_env; then
      startup_env_restart_required="1"
    else
      rc=$?
      if [ "$rc" -ne 10 ]; then
        exit "$rc"
      fi
    fi
  else
    echo "startup_compose_update=skip reason=compose_missing"
  fi
  echo "--- sandbox_mode_apply ---"
  if [ "$auto_disable_sandbox_without_docker" = "1" ]; then
    if [ "$docker_present" != "1" ]; then
      patch_host_configs="1"
      sandbox_restart_required="1"
    fi

    if [ -s "$container_names_file" ]; then
      while IFS= read -r container_name; do
        [ -n "$container_name" ] || continue
        if container_has_docker "$container_name"; then
          echo "container=${container_name} container_sandbox_update=skip reason=container_has_docker"
          continue
        fi
        patch_host_configs="1"
        sandbox_restart_required="1"
        if apply_container_sandbox_mode "$container_name" "$sandbox_mode_target"; then
          sandbox_fix_applied="1"
        else
          rc=$?
          if [ "$rc" -ne 10 ]; then
            exit "$rc"
          fi
        fi
      done < "$container_names_file"
    fi

    if [ "$patch_host_configs" = "1" ]; then
      config_found="0"
      for f in "${cfg_files[@]}"; do
        if [ -f "$f" ]; then
          config_found="1"
          if apply_sandbox_mode "$f" "$sandbox_mode_target"; then
            sandbox_fix_applied="1"
          else
            rc=$?
            if [ "$rc" -ne 10 ]; then
              exit "$rc"
            fi
          fi
        else
          echo "missing $f"
        fi
      done
      if [ "$config_found" != "1" ]; then
        echo "sandbox_mode_apply=skip reason=no_host_config_files"
      fi
    else
      echo "sandbox_mode_apply=skip reason=no_runtime_need_detected"
    fi
  else
    echo "sandbox_mode_apply=skip reason=disabled"
  fi
  echo "--- config_permissions_apply ---"
  for f in "${cfg_files[@]}"; do
    if [ -f "$f" ]; then
      chmod 600 "$f"
      stat -c '%a %U:%G %n' "$f"
    fi
  done
  echo "--- search_provider_apply ---"
  for f in "${cfg_files[@]}"; do
    if [ -f "$f" ]; then
      if apply_search_provider "$f"; then
        search_provider_fix_applied="1"
        search_provider_restart_required="1"
      else
        rc=$?
        if [ "$rc" -ne 10 ]; then
          exit "$rc"
        fi
      fi
    fi
  done

  if command -v docker >/dev/null 2>&1; then
    echo "--- container_config_permissions_apply ---"
    while IFS= read -r container_name; do
      [ -n "$container_name" ] || continue
      echo "container=${container_name}"
      set +e
      docker exec -u 0 "$container_name" sh -lc '
        set -e
        target="/home/node/.openclaw/openclaw.json"
        if [ -f "$target" ]; then
          chown 1000:1000 "$target"
          chmod 600 "$target"
          if command -v stat >/dev/null 2>&1; then
            stat -c "%a %U:%G %n" "$target" || true
          else
            ls -l "$target" || true
          fi
        else
          echo "missing $target"
        fi
      '
      docker_rc=$?
      set -e
      echo "container_apply_rc=${docker_rc}"
    done </tmp/openclaw_docker_names.txt
  fi
  if [ "${startup_env_restart_required:-0}" = "1" ] || [ "$sandbox_fix_applied" = "1" ] || [ "$sandbox_restart_required" = "1" ] || [ "$search_provider_fix_applied" = "1" ] || [ "$search_provider_restart_required" = "1" ]; then
    restart_openclaw_runtime
  else
    echo "--- openclaw_runtime_restart ---"
    echo "openclaw_runtime_restart=skip reason=no_sandbox_runtime_restart_needed"
  fi
fi

echo "--- compose_ports_after ---"
print_compose_ports
print_startup_env_state
echo "--- listener_after ---"
ss -ltnp 2>/dev/null | grep -E "(:${gateway_port}|:${bridge_port})" || true
if [ -n "$compose_backup" ]; then
  echo "compose_backup=${compose_backup}"
fi

echo "--- config_permissions_after ---"
for f in "${cfg_files[@]}"; do
  print_config_state "$f"
done
echo "--- container_config_after ---"
if [ -s "$container_names_file" ]; then
  while IFS= read -r container_name; do
    [ -n "$container_name" ] || continue
    print_container_config_state "$container_name"
  done < "$container_names_file"
else
  echo "openclaw_containers=none"
fi
REMOTE

remote_script="${remote_script/__MODE_B64__/$mode_b64}"
remote_script="${remote_script/__OPENCLAW_DIR_B64__/$openclaw_dir_b64}"
remote_script="${remote_script/__OPENCLAW_GATEWAY_PORT_B64__/$gateway_port_b64}"
remote_script="${remote_script/__OPENCLAW_BRIDGE_PORT_B64__/$bridge_port_b64}"
remote_script="${remote_script/__OPENCLAW_COMPILE_CACHE_B64__/$compile_cache_b64}"
remote_script="${remote_script/__OPENCLAW_NO_RESPAWN_B64__/$no_respawn_b64}"
remote_script="${remote_script/__OPENCLAW_ENV_FILE_B64__/$env_file_b64}"
remote_script="${remote_script/__LOCKDOWN_GATEWAY_BIND_B64__/$lockdown_b64}"
remote_script="${remote_script/__CONFIG_PATHS_B64__/$config_paths_b64}"
remote_script="${remote_script/__SANDBOX_MODE_TARGET_B64__/$sandbox_mode_target_b64}"
remote_script="${remote_script/__AUTO_DISABLE_SANDBOX_B64__/$auto_disable_sandbox_b64}"

log "Запуск workflow openclaw_gateway_repair: mode=${MODE}, host=${OPENCLAW_HOST}"
{
  echo "# OpenClaw Gateway Repair"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${OPENCLAW_HOST}"
  echo "Режим: ${MODE}"
  echo
  run_remote_script "$OPENCLAW_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "Workflow openclaw_gateway_repair завершён"
log "Отчет: ${REPORT_FILE}"
