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

load_optional_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

load_schedule_contract() {
  local root_dir="$1"
  local contract_file="${SCHEDULE_CONTRACT_FILE:-$root_dir/configs/schedule_contract.env}"
  load_optional_env_file "$contract_file"
}

prepare_larisa_remote_todo_snapshot() {
  local root_dir="$1"
  local ssh_helper="$root_dir/ops/ssh_happ.sh"
  local snapshot_dir=""
  local snapshot_file=""

  LARISA_REMOTE_TODO_STATE_DIR=""

  if [[ -n "${LARISA_TODO_SNAPSHOT_FILE:-}" ]] || [[ -n "${TODO_TASKS_SNAPSHOT_FILE:-}" ]] || [[ -n "${LARISA_TODO_STATE_DIR:-}" ]] || [[ -n "${TODO_STATE_DIR:-}" ]] || [[ -n "${LARISA_TODO_TOKEN:-}" ]] || [[ -n "${TODO_TOKEN:-}" ]]; then
    return 0
  fi

  if [[ ! -x "$ssh_helper" ]]; then
    return 0
  fi

  snapshot_dir="$(mktemp -d "${TMPDIR:-/tmp}/larisa_todo_snapshot.XXXXXX")"
  snapshot_file="$snapshot_dir/tasks_snapshot.json"
  if "$ssh_helper" primary "sudo -n bash -lc 'set -euo pipefail
state_dir=\"\"
for env_file in /root/.openclaw/workspace/todo-integration/.env.runtime /etc/openclaw/todo.env; do
  [[ -f \"\$env_file\" ]] || continue
  value=\$(awk -F= '\''/^TODO_STATE_DIR=/{print substr(\$0, index(\$0, \"=\") + 1)}'\'' \"\$env_file\" | tail -n 1)
  if [[ -n \"\$value\" ]]; then
    state_dir=\"\$value\"
    break
  fi
done
state_dir=\${state_dir:-/home/node/.openclaw/todo-integration-data}
host_state_dir=\"\$state_dir\"
if [[ ! -d \"\$host_state_dir\" && \"\$state_dir\" == /home/node/.openclaw/* ]]; then
  host_state_dir=\"/root\${state_dir#/home/node}\"
fi
snapshot_path=\"\$host_state_dir/tasks_snapshot.json\"
cat \"\$snapshot_path\"'" >"$snapshot_file" 2>/dev/null; then
    export LARISA_TODO_STATE_DIR="$snapshot_dir"
    LARISA_REMOTE_TODO_STATE_DIR="$snapshot_dir"
    log "larisa_todo: подключен live snapshot задач с primary host"
    return 0
  fi

  rm -rf "$snapshot_dir"
  return 0
}

cleanup_larisa_remote_todo_snapshot() {
  if [[ -n "${LARISA_REMOTE_TODO_STATE_DIR:-}" ]] && [[ -d "${LARISA_REMOTE_TODO_STATE_DIR:-}" ]]; then
    rm -rf "$LARISA_REMOTE_TODO_STATE_DIR"
  fi
}

cloudbot_runtime_files() {
  cat <<'EOF'
agents/__init__.py
agents/larisa_ivanovna
agents/lev_petrovich
agents/sales_agent
apps/finansist
apps/larisa_ivanovna
apps/lev_petrovich
cloudbot/__init__.py
cloudbot/business_day.py
cloudbot/compat
cloudbot/devops/sales_dispatch_health.py
cloudbot/providers/__init__.py
cloudbot/providers/bitrix
cloudbot/providers/bitrix_provider.py
cloudbot/providers/wazzup_provider.py
cloudbot/skills/__init__.py
cloudbot/skills/bitrix_sales_data.py
cloudbot/skills/web_search
cloudbot/skills/web_search.py
infra/orchestrator/lib.sh
infra/orchestrator/run_workflow.sh
infra/orchestrator/workflows/larisa_daily_brief.sh
infra/orchestrator/workflows/larisa_midday_replan.sh
infra/orchestrator/workflows/sales_brief.sh
infra/orchestrator/workflows/sales_followup.sh
infra/orchestrator/workflows/sales_morning_report.sh
infra/orchestrator/workflows/sales_morning_report_check.sh
infra/orchestrator/workflows/sales_weekly_review.sh
scripts/run_sales_copilot.py
shared/contracts
shared/time
EOF
}

require_clean_release_checkout() {
  local repo_root="$1"
  local git_top

  git_top="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "$git_top" ]]; then
    fail "Каталог не является git-репозиторием: $repo_root"
  fi

  if [[ "${ALLOW_DIRTY_DEPLOY:-0}" == "1" ]]; then
    log "release_checkout: пропускаю проверку чистоты рабочего дерева (ALLOW_DIRTY_DEPLOY=1)"
    return 0
  fi

  if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
    fail "Рабочее дерево не чистое. Для осознанного обхода укажи ALLOW_DIRTY_DEPLOY=1."
  fi
}

require_release_on_origin() {
  local repo_root="$1"
  local branch_name="$2"
  local head_sha="$3"
  local remote_sha=""

  if [[ -z "$branch_name" || "$branch_name" == "HEAD" ]]; then
    fail "Release deploy запрещен из detached HEAD. Нужна живая ветка с upstream."
  fi

  if [[ "${ALLOW_UNPUSHED_RELEASE:-0}" == "1" ]]; then
    log "release_origin: пропускаю проверку commit на origin/${branch_name} (ALLOW_UNPUSHED_RELEASE=1)"
    return 0
  fi

  if ! git -C "$repo_root" fetch origin "$branch_name" --prune >/dev/null 2>&1; then
    fail "Не удалось получить origin/${branch_name} перед release deploy."
  fi

  remote_sha="$(git -C "$repo_root" rev-parse --verify "origin/${branch_name}" 2>/dev/null || true)"
  if [[ -z "$remote_sha" ]]; then
    fail "На origin отсутствует ветка ${branch_name}. Сначала push, потом deploy."
  fi

  if [[ "$head_sha" != "$remote_sha" ]]; then
    fail "Локальный HEAD (${head_sha}) не совпадает с origin/${branch_name} (${remote_sha}). Сначала push или укажи ALLOW_UNPUSHED_RELEASE=1."
  fi
}

acquire_remote_lock() {
  local host="$1"
  local lock_path="$2"
  local owner="$3"
  local lock_q
  local owner_q

  printf -v lock_q '%q' "$lock_path"
  printf -v owner_q '%q' "$owner"

  run_remote_script "$host" "
set -euo pipefail
lock_path=${lock_q}
owner=${owner_q}

if mkdir \"\$lock_path\" 2>/dev/null; then
  printf '%s\n' \"\$owner\" >\"\$lock_path/owner\"
  date '+%F %T %Z' >\"\$lock_path/acquired_at\"
  echo \"deploy_lock=acquired\"
  exit 0
fi

echo \"Release lock уже занят: \$lock_path\" >&2
if [[ -f \"\$lock_path/owner\" ]]; then
  echo \"owner=\$(cat \"\$lock_path/owner\")\" >&2
fi
if [[ -f \"\$lock_path/acquired_at\" ]]; then
  echo \"acquired_at=\$(cat \"\$lock_path/acquired_at\")\" >&2
fi
exit 42
"
}

release_remote_lock() {
  local host="$1"
  local lock_path="$2"
  local lock_q

  printf -v lock_q '%q' "$lock_path"

  run_remote_script "$host" "
set -euo pipefail
lock_path=${lock_q}
rm -rf \"\$lock_path\"
echo \"deploy_lock=released\"
"
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
