#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/remote-ops.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

target="${1:-primary}"
shift || true

case "$target" in
  primary) host="${PRIMARY_HOST:-${OPENCLAW_HOST:-}}" ;;
  reserve) host="${RESERVE_HOST:-}" ;;
  *) echo "Использование: $0 [primary|reserve] [remote command...]" >&2; exit 2 ;;
esac

if [[ -z "$host" ]]; then
  echo "Не задан host для target=${target} в ${ENV_FILE}" >&2
  exit 1
fi

: "${SSH_USER:=ops}"
: "${SSH_PORT:=22}"
: "${SSH_KEY_PATH:=$HOME/.ssh/id_ed25519}"
: "${SSH_WRAP_LOGIN_SHELL:=1}"

if [[ ! -f "$SSH_KEY_PATH" ]]; then
  fallback_key="$HOME/.ssh/temp_migration_key"
  if [[ -f "$fallback_key" ]]; then
    SSH_KEY_PATH="$fallback_key"
  else
    echo "SSH ключ не найден: $SSH_KEY_PATH (fallback тоже отсутствует: $fallback_key)" >&2
    exit 1
  fi
fi

if [[ "$#" -gt 0 ]]; then
  remote_cmd="$*"
  if [[ "$SSH_WRAP_LOGIN_SHELL" == "1" ]]; then
    # Канонический путь remote-команд идёт через login shell, чтобы серверный env
    # и startup-переменные OpenClaw применялись одинаково в интерактивных и batch-сценариях.
    printf -v remote_cmd '%q' "$remote_cmd"
    exec ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=7 \
      "${SSH_USER}@${host}" "bash -lc ${remote_cmd}"
  fi
  exec ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=7 \
    "${SSH_USER}@${host}" "$*"
fi

exec ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=7 \
  "${SSH_USER}@${host}"
