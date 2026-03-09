#!/usr/bin/env bash
set -euo pipefail

: "${TZ:=Europe/Moscow}"
export TZ

log() {
  printf "[%s] %s\n" "$(date '+%F %T %Z')" "$*"
}

fail() {
  log "ОШИБКА: $*"
  exit 1
}

require_env() {
  local v
  for v in "$@"; do
    if [[ -z "${!v:-}" ]]; then
      fail "Не задана обязательная переменная: $v"
    fi
  done
}

run_cmd() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "[DRY-RUN] $*"
    return 0
  fi
  eval "$*"
}

run_remote() {
  local host="$1"
  local cmd="$2"

  require_env SSH_USER SSH_KEY_PATH SSH_PORT

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "[DRY-RUN][${host}] ${cmd}"
    return 0
  fi

  ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    "${SSH_USER}@${host}" "$cmd"
}

run_remote_script() {
  local host="$1"
  local script="$2"

  require_env SSH_USER SSH_KEY_PATH SSH_PORT

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "[DRY-RUN][${host}] <<'REMOTE'"
    printf '%s\n' "$script"
    log "[DRY-RUN][${host}] REMOTE"
    return 0
  fi

  ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    "${SSH_USER}@${host}" 'bash -se' <<REMOTE
${script}
REMOTE
}
