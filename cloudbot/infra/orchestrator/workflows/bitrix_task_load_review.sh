#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

: "${TZ:=Europe/Moscow}"
export TZ

log "bitrix_task_load_review: старт"

set +e
(
  cd "$ROOT_DIR"
  python3 "$ROOT_DIR/scripts/bitrix_task_load_review.py" --json
)
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "bitrix_task_load_review: ошибка (rc=${rc})"
  exit "$rc"
fi

log "bitrix_task_load_review: успешно"
