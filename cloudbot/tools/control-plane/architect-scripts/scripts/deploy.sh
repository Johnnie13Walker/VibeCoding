#!/usr/bin/env bash

set -euo pipefail

TZ="${TZ:-Europe/Moscow}"
export TZ

DRY_RUN="${DRY_RUN:-1}"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

run_step() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    log "DRY-RUN: $*"
  else
    log "RUN: $*"
    "$@"
  fi
}

main() {
  log "Старт deploy-шаблона Cloudbot"
  log "Режим DRY_RUN=${DRY_RUN}"

  if [[ ! -d ".git" ]]; then
    log "Git-репозиторий не найден. Останов."
    exit 1
  fi

  run_step git status --short

  log "Шаблон deploy создан. Добавь сюда проектные шаги обновления, пересборки и перезапуска."
  log "По умолчанию скрипт безопасен и ничего не меняет без DRY_RUN=0."
}

main "$@"
