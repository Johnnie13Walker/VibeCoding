#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_NODE="${OPENCLAW_NODE:-node}"
OPENCLAW_RUNNER="${OPENCLAW_RUNNER:-scripts/run-node.mjs}"

HEALTH_JOB_NAME="${HEALTH_JOB_NAME:-healthcheck-daily}"
STATUS_JOB_NAME="${STATUS_JOB_NAME:-daily-status-report}"
HEALTH_CRON_EXPR="${HEALTH_CRON_EXPR:-0 9 * * *}"
STATUS_CRON_EXPR="${STATUS_CRON_EXPR:-30 9 * * *}"
CRON_TZ="${CRON_TZ:-Europe/Moscow}"
STATUS_DESCRIPTION="${STATUS_DESCRIPTION:-Ежедневный статус-отчет в 09:30 МСК}"
STATUS_MESSAGE="${STATUS_MESSAGE:-Сформируй ежедневный статус-отчет за последние 24 часа в формате: ОК или есть проблемы. Если есть проблемы, кратко укажи что сломано, причину, что уже сделано, что осталось и когда следующий чек.}"
MODE="${1:-inspect}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

status_description_b64="$(printf '%s' "$STATUS_DESCRIPTION" | base64 | tr -d '\n')"
status_message_b64="$(printf '%s' "$STATUS_MESSAGE" | base64 | tr -d '\n')"

remote_script=$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow

openclaw_dir='${OPENCLAW_DIR}'
node_bin='${OPENCLAW_NODE}'
runner='${OPENCLAW_RUNNER}'
health_name='${HEALTH_JOB_NAME}'
status_name='${STATUS_JOB_NAME}'
health_cron='${HEALTH_CRON_EXPR}'
status_cron='${STATUS_CRON_EXPR}'
cron_tz='${CRON_TZ}'
mode='${MODE}'
status_description="\$(printf '%s' '${status_description_b64}' | base64 -d)"
status_message="\$(printf '%s' '${status_message_b64}' | base64 -d)"

if ! command -v jq >/dev/null 2>&1; then
  echo 'ОШИБКА: на хосте не найден jq' >&2
  exit 1
fi

if [ ! -d "\$openclaw_dir" ]; then
  echo "ОШИБКА: каталог OpenClaw не найден: \$openclaw_dir" >&2
  exit 1
fi

cd "\$openclaw_dir"

run_openclaw() {
  if [ -f dist/entry.js ]; then
    "\$node_bin" dist/entry.js "\$@"
  else
    OPENCLAW_RUNNER_LOG=0 "\$node_bin" "\$runner" "\$@"
  fi
}

extract_json() {
  sed -n '/^[[:space:]]*{/,\$p'
}

load_jobs_json() {
  local raw json
  raw="\$(run_openclaw cron list --all --json 2>&1 || true)"
  json="\$(printf '%s\n' "\$raw" | extract_json)"
  if [ -z "\$json" ]; then
    echo "ОШИБКА: не удалось выделить JSON из вывода cron list" >&2
    printf '%s\n' "\$raw" >&2
    return 1
  fi
  printf '%s\n' "\$json"
}

pick_job_id_by_name() {
  local jobs_json="\$1"
  local job_name="\$2"
  printf '%s\n' "\$jobs_json" | jq -r --arg name "\$job_name" '.jobs[]? | select(.name == \$name) | .id' | head -n1
}

print_targets() {
  local jobs_json="\$1"
  printf '%s\n' "\$jobs_json" | jq --arg health "\$health_name" --arg status "\$status_name" '
    [
      .jobs[]?
      | select(.name == \$health or .name == \$status)
      | {
          id,
          name,
          enabled,
          schedule: {
            kind: .schedule.kind,
            expr: (.schedule.expr // null),
            tz: (.schedule.tz // null)
          },
          sessionTarget,
          payload: {
            kind: .payload.kind,
            message: (.payload.message // .payload.text // null)
          },
          delivery: {
            mode: (.delivery.mode // null),
            channel: (.delivery.channel // null),
            to: (.delivery.to // null),
            accountId: (.delivery.accountId // null),
            bestEffort: (.delivery.bestEffort // null)
          },
          state: {
            nextRunAtMs: (.state.nextRunAtMs // null),
            lastRunAtMs: (.state.lastRunAtMs // null),
            lastRunStatus: (.state.lastRunStatus // null),
            lastDelivered: (.state.lastDelivered // null)
          }
        }
    ]'
}

jobs_json="\$(load_jobs_json)"
health_id="\$(pick_job_id_by_name "\$jobs_json" "\$health_name")"
status_id="\$(pick_job_id_by_name "\$jobs_json" "\$status_name")"

echo "Хост: \$(hostname)"
echo "Каталог OpenClaw: \$openclaw_dir"
echo "Найдены job: health_id=\${health_id:-<none>}, status_id=\${status_id:-<none>}"
echo "Текущее состояние целевых job:"
print_targets "\$jobs_json"

if [ "\$mode" = "inspect" ]; then
  exit 0
fi

if [ -z "\$health_id" ]; then
  echo "ОШИБКА: не найден обязательный job '\$health_name'" >&2
  exit 1
fi

echo "Обновляю расписание healthcheck: \$health_id -> '\$health_cron' (\$cron_tz)"
run_openclaw cron edit "\$health_id" \
  --cron "\$health_cron" \
  --tz "\$cron_tz" \
  --description "Ежедневный healthcheck в 09:00 МСК" >/tmp/openclaw_health_schedule_edit.json
sed -n '/^[[:space:]]*{/,\$p' /tmp/openclaw_health_schedule_edit.json || true

jobs_json="\$(load_jobs_json)"
status_id="\$(pick_job_id_by_name "\$jobs_json" "\$status_name")"

if [ -n "\$status_id" ]; then
  echo "Обновляю существующий status job: \$status_id -> '\$status_cron' (\$cron_tz)"
  run_openclaw cron edit "\$status_id" \
    --cron "\$status_cron" \
    --tz "\$cron_tz" \
    --message "\$status_message" \
    --description "\$status_description" >/tmp/openclaw_status_schedule_edit.json
  sed -n '/^[[:space:]]*{/,\$p' /tmp/openclaw_status_schedule_edit.json || true
else
  echo "Создаю status job '\$status_name' на '\$status_cron' (\$cron_tz)"
  health_delivery_mode="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.delivery.mode // "announce")')"
  health_delivery_channel="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.delivery.channel // "")')"
  health_delivery_to="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.delivery.to // "")')"
  health_delivery_account="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.delivery.accountId // "")')"
  health_best_effort="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.delivery.bestEffort // false)')"
  health_wake_mode="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.wakeMode // "now")')"
  health_agent_id="\$(printf '%s\n' "\$jobs_json" | jq -r --arg id "\$health_id" '.jobs[]? | select(.id == \$id) | (.agentId // "")')"

  add_cmd=(
    cron add
    --name "\$status_name"
    --description "\$status_description"
    --session isolated
    --wake "\$health_wake_mode"
    --cron "\$status_cron"
    --tz "\$cron_tz"
    --message "\$status_message"
  )

  if [ "\$health_delivery_mode" = "none" ]; then
    add_cmd+=(--no-deliver)
  else
    add_cmd+=(--announce)
  fi
  if [ -n "\$health_delivery_channel" ]; then
    add_cmd+=(--channel "\$health_delivery_channel")
  fi
  if [ -n "\$health_delivery_to" ]; then
    add_cmd+=(--to "\$health_delivery_to")
  fi
  if [ -n "\$health_delivery_account" ]; then
    add_cmd+=(--account "\$health_delivery_account")
  fi
  if [ "\$health_best_effort" = "true" ]; then
    add_cmd+=(--best-effort-deliver)
  fi
  if [ -n "\$health_agent_id" ]; then
    add_cmd+=(--agent "\$health_agent_id")
  fi

  run_openclaw "\${add_cmd[@]}" >/tmp/openclaw_status_schedule_add.json
  sed -n '/^[[:space:]]*{/,\$p' /tmp/openclaw_status_schedule_add.json || true
fi

jobs_json="\$(load_jobs_json)"
echo "Итоговое состояние целевых job:"
print_targets "\$jobs_json"
REMOTE
)

log "Обновление расписания OpenClaw cron (${MODE}) на хосте ${OPENCLAW_HOST}"
run_remote_script "$OPENCLAW_HOST" "$remote_script"
log "Обновление расписания завершено"
