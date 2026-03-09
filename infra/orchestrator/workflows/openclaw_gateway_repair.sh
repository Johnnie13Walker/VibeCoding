#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
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
REPORT_FILE="$REPORT_DIR/openclaw_gateway_repair_${STAMP}.txt"
mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
openclaw_dir="${OPENCLAW_DIR:-/opt/openclaw}"

run_openclaw() {
  if [ -f "${openclaw_dir}/dist/entry.js" ] && command -v node >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && OPENCLAW_RUNNER_LOG=0 node dist/entry.js "$@")
    return $?
  fi
  if [ -f "${openclaw_dir}/scripts/run-node.mjs" ] && command -v node >/dev/null 2>&1; then
    (cd "${openclaw_dir}" && OPENCLAW_RUNNER_LOG=0 node scripts/run-node.mjs "$@")
    return $?
  fi
  if command -v openclaw >/dev/null 2>&1; then
    openclaw "$@"
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

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=${mode}"

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

print_cmd "openclaw_status" run_openclaw status
print_cmd "openclaw_gateway_status" run_openclaw gateway status
print_cmd "openclaw_doctor_non_interactive" run_openclaw doctor --non-interactive

echo "--- config_permissions_before ---"
declare -a cfg_files
cfg_files=(
  "/root/.openclaw/openclaw.json"
  "/home/node/.openclaw/openclaw.json"
  "/home/ops/.openclaw/openclaw.json"
)
for f in "${cfg_files[@]}"; do
  if [ -f "$f" ]; then
    stat -c '%a %U:%G %n' "$f"
  else
    echo "missing $f"
  fi
done

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
  print_cmd "openclaw_doctor_repair" run_openclaw doctor --repair
  echo "--- config_permissions_apply ---"
  for f in "${cfg_files[@]}"; do
    if [ -f "$f" ]; then
      chmod 600 "$f"
      stat -c '%a %U:%G %n' "$f"
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
fi

echo "--- config_permissions_after ---"
for f in "${cfg_files[@]}"; do
  if [ -f "$f" ]; then
    stat -c '%a %U:%G %n' "$f"
  else
    echo "missing $f"
  fi
done
REMOTE

remote_script="${remote_script/__MODE_B64__/$mode_b64}"

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
