#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST

MODE="${1:-apply}"
APPLY_SCRIPT="$ROOT_DIR/infra/orchestrator/workflows/todo-digest-remediate.apply.remote.sh"
SMOKE_SCRIPT="$ROOT_DIR/infra/orchestrator/workflows/todo-digest-remediate.smoke.remote.sh"

run_apply() {
  log "Применение фиксов todo-digest на ${PRIMARY_HOST}"
  [[ -f "$APPLY_SCRIPT" ]] || fail "Не найден скрипт: $APPLY_SCRIPT"
  run_remote_script "$PRIMARY_HOST" "$(cat "$APPLY_SCRIPT")"
}

run_smoke() {
  log "Smoke-проверка todo-digest на ${PRIMARY_HOST}"
  [[ -f "$SMOKE_SCRIPT" ]] || fail "Не найден скрипт: $SMOKE_SCRIPT"
  run_remote_script "$PRIMARY_HOST" "$(cat "$SMOKE_SCRIPT")"
}

case "$MODE" in
  apply)
    run_apply
    ;;
  smoke)
    run_smoke
    ;;
  full)
    run_apply
    run_smoke
    ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: apply, smoke, full)"
    ;;
esac
