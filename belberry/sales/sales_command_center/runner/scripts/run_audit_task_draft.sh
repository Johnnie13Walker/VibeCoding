#!/usr/bin/env bash
# Умная постановка задачи под выбранного менеджера (пол/имя/легенда перехвата).
# Веб дёргает синхронно: run_audit_task_draft.sh <audit_id> <responsible_id>.
# Печатает в stdout одну строку JSON {title, description} (или {error}). БЕЗ flock —
# это короткий on-demand вызов, не cron.
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

SCC_ENV_FILE="${SCC_ENV_FILE:-/etc/scc/scc.env}"
if [ -f "$SCC_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SCC_ENV_FILE"
  set +a
fi

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RUNNER_DIR"
.venv/bin/python -m src.audit_task_draft "$@"
