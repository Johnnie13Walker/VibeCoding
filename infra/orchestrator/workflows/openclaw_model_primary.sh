#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
MODE="${1:-inspect}"
TARGET_MODEL="${2:-${TARGET_MODEL:-openai/gpt-5.3-codex}}"
CONFIG_PATHS="${CONFIG_PATHS:-/root/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json}"
CONFIG_OWNER="${CONFIG_OWNER:-1000:1000}"
CONFIG_MODE="${CONFIG_MODE:-0644}"
GATEWAY_CONTAINER_NAME="${GATEWAY_CONTAINER_NAME:-openclaw-openclaw-gateway-1}"
RESTART_GATEWAY="${RESTART_GATEWAY:-1}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

target_model_b64="$(printf '%s' "$TARGET_MODEL" | base64 | tr -d '\n')"
config_paths_b64="$(printf '%s' "$CONFIG_PATHS" | base64 | tr -d '\n')"
config_owner_b64="$(printf '%s' "$CONFIG_OWNER" | base64 | tr -d '\n')"
config_mode_b64="$(printf '%s' "$CONFIG_MODE" | base64 | tr -d '\n')"
gateway_container_b64="$(printf '%s' "$GATEWAY_CONTAINER_NAME" | base64 | tr -d '\n')"
restart_gateway_b64="$(printf '%s' "$RESTART_GATEWAY" | base64 | tr -d '\n')"

remote_script=$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow

mode='${MODE}'
target_model="\$(printf '%s' '${target_model_b64}' | base64 -d)"
config_paths_raw="\$(printf '%s' '${config_paths_b64}' | base64 -d)"
config_owner="\$(printf '%s' '${config_owner_b64}' | base64 -d)"
config_mode="\$(printf '%s' '${config_mode_b64}' | base64 -d)"
gateway_container="\$(printf '%s' '${gateway_container_b64}' | base64 -d)"
restart_gateway="\$(printf '%s' '${restart_gateway_b64}' | base64 -d)"

if ! command -v jq >/dev/null 2>&1; then
  echo 'ОШИБКА: на хосте не найден jq' >&2
  exit 1
fi

IFS=' ' read -r -a config_paths <<< "\$config_paths_raw"
found=0
updated=0

for cfg in "\${config_paths[@]}"; do
  if [ ! -f "\$cfg" ]; then
    continue
  fi

  found=1
  current="\$(jq -r '.agents.defaults.model.primary // empty' "\$cfg" 2>/dev/null || true)"
  echo "config_file=\$cfg"
  echo "current_model=\${current:-<empty>}"

  if [ "\$mode" = "apply" ]; then
    ts="\$(date '+%Y%m%d_%H%M%S_%Z')"
    backup="\${cfg}.bak.\${ts}"
    cp -a "\$cfg" "\$backup"

    tmp="\$(mktemp)"
    jq --arg model "\$target_model" \
      '.agents = (.agents // {}) | .agents.defaults = (.agents.defaults // {}) | .agents.defaults.model = (.agents.defaults.model // {}) | .agents.defaults.model.primary = \$model' \
      "\$cfg" > "\$tmp"
    jq -e . "\$tmp" >/dev/null

    chown "\$config_owner" "\$tmp" || true
    chmod "\$config_mode" "\$tmp" || true
    mv "\$tmp" "\$cfg"
    chown "\$config_owner" "\$cfg" || true
    chmod "\$config_mode" "\$cfg" || true
    after="\$(jq -r '.agents.defaults.model.primary // empty' "\$cfg")"
    perms="\$(stat -c '%U:%G %a' "\$cfg" 2>/dev/null || true)"
    echo "updated_model=\${after:-<empty>}"
    echo "updated_perms=\${perms:-<unknown>}"
    echo "backup_file=\$backup"

    if [ "\$after" != "\$target_model" ]; then
      echo "ОШИБКА: после обновления в \$cfg модель не совпала с целевой" >&2
      exit 1
    fi
    updated=\$((updated + 1))
  fi

  echo "---"
done

if [ "\$found" -eq 0 ]; then
  echo "ОШИБКА: не найден ни один конфиг из списка: \$config_paths_raw" >&2
  exit 1
fi

if [ "\$mode" = "inspect" ]; then
  echo "inspect_done=1"
else
  if [ "\$restart_gateway" = "1" ]; then
    if command -v docker >/dev/null 2>&1 && docker inspect "\$gateway_container" >/dev/null 2>&1; then
      echo "gateway_restart=begin container=\$gateway_container"
      check_since="\$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
      docker restart "\$gateway_container" >/dev/null
      sleep 2

      model_line=""
      for _ in 1 2 3 4 5 6 7 8 9 10; do
        clean_tail="\$(docker logs --since "\$check_since" --tail 240 "\$gateway_container" 2>&1 | sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g')"
        model_line="\$(printf '%s\n' "\$clean_tail" | grep -F 'agent model:' | tail -n1 || true)"
        if [ -n "\$model_line" ]; then
          break
        fi
        sleep 1
      done
      echo "gateway_model_line=\${model_line:-<missing>}"

      if ! printf '%s\n' "\$model_line" | grep -F "\$target_model" >/dev/null 2>&1; then
        echo "ОШИБКА: после рестарта gateway не сообщил целевую модель (\$target_model)" >&2
        exit 1
      fi
    else
      echo "gateway_restart=skip reason=container_not_found name=\$gateway_container"
    fi
  else
    echo "gateway_restart=skip reason=disabled"
  fi

  echo "apply_done=1 updated_files=\$updated target_model=\$target_model"
fi
REMOTE
)

log "Проверка/обновление primary-модели OpenClaw (${MODE}) на хосте ${OPENCLAW_HOST}"
run_remote_script "$OPENCLAW_HOST" "$remote_script"
log "Workflow openclaw_model_primary завершён"
