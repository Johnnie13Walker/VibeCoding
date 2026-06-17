#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"
load_schedule_contract "$ROOT_DIR"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
OPENCLAW_NODE="${OPENCLAW_NODE:-node}"
OPENCLAW_RUNNER="${OPENCLAW_RUNNER:-scripts/run-node.mjs}"
OPENCLAW_COMPILE_CACHE_DIR="${OPENCLAW_COMPILE_CACHE_DIR:-/var/tmp/openclaw-compile-cache}"
OPENCLAW_NO_RESPAWN="${OPENCLAW_NO_RESPAWN:-1}"
OPENCLAW_CLI_ATTEMPTS="${OPENCLAW_CLI_ATTEMPTS:-3}"
OPENCLAW_CLI_RETRY_SLEEP="${OPENCLAW_CLI_RETRY_SLEEP:-2}"

HEALTH_JOB_NAME="${HEALTH_JOB_NAME:-healthcheck-daily}"
STATUS_JOB_NAME="${STATUS_JOB_NAME:-daily-status-report}"
HEALTH_CRON_EXPR="${HEALTH_CRON_EXPR:-${OPENCLAW_HEALTH_CRON_MSK:-0 9 * * *}}"
STATUS_CRON_EXPR="${STATUS_CRON_EXPR:-${OPENCLAW_STATUS_CRON_MSK:-30 9 * * *}}"
HEALTH_DELIVERY_MODE="${HEALTH_DELIVERY_MODE:-${OPENCLAW_HEALTH_DELIVERY_MODE:-none}}"
STATUS_DELIVERY_MODE="${STATUS_DELIVERY_MODE:-${OPENCLAW_STATUS_DELIVERY_MODE:-announce}}"
CRON_TZ="${CRON_TZ:-Europe/Moscow}"
HEALTH_DESCRIPTION="${HEALTH_DESCRIPTION:-Ежедневный healthcheck в 09:00 МСК}"
HEALTH_MESSAGE="${HEALTH_MESSAGE:-Выполни ежедневный health-check в режиме read-only как внутренний upstream-диагностический прогон для финального утреннего отчёта. При зелёном статусе не дублируй полноценный пользовательский infra-summary, который должен прийти отдельным итоговым отчётом. Разделяй активные проблемы и наблюдения/техдолг. missing scope: operator.read в openclaw gateway probe или openclaw status --deep трактуй как деградированную глубину диагностики, а не как недоступность gateway. warning multi_user_heuristic трактуй как архитектурный риск/техдолг, а не как активную поломку, если groupPolicy не open, доступ ограничен allowlist и нет фактических сбоев gateway, Telegram, cron или доставки. Доступное обновление OpenClaw само по себе не авария, а maintenance backlog. Не выдавай API OK за пользовательский сценарий OK: отдельно различай platform status, API/integration status и user-facing capability status. Если интеграция давно известна и подтверждена, не выводи её в блоке Новые API. Для web search отдельно различай Web Search provider, web_search skill и Web search для Ларисы.}"
STATUS_DESCRIPTION="${STATUS_DESCRIPTION:-Ежедневный статус-отчет в 09:30 МСК}"
STATUS_MESSAGE="${STATUS_MESSAGE:-Сформируй ОДИН итоговый утренний отчёт в Telegram в формате управленческого дашборда, а не технического лога. Смысл и данные не меняй, меняй только структуру и подачу. Полностью убери англицизмы и используй русский управленческий язык. Все заголовки блоков и разделов делай жирными: Сводка одним взглядом, Что важно сейчас, Общий статус, Инфраструктура, OpenClaw / OpenCloud, Интеграции, Пользовательские возможности, Планировщик, Безопасность, Риски и техдолг, Изменения за 24 часа, Итог. Названия ключевых строк в верхней сводке тоже выделяй жирным. В начале всегда делай блок Сводка одним взглядом: Статус системы, Индекс здоровья, Критические проблемы, Предупреждения, Не настроено, затем 1-2 строки управленческого вывода. После сводки обязательно добавляй блок Что важно сейчас с 3-4 короткими пунктами. Далее используй именно такую структуру: Общий статус, Инфраструктура, OpenClaw / OpenCloud, Интеграции, Пользовательские возможности, Планировщик, Безопасность, Риски и техдолг, Изменения за 24 часа, Итог. Блок Изменения за 24 часа показывай только если данные доступны; если нет, пропускай его. Во всех блоках используй единую систему статусов: 🟢 Работает, 🟡 Предупреждение, 🔴 Ошибка, ⚪ Не настроено. Не используй слова fail, warning, running, not configured, health score, gateway reachable и подобные; переводи их на русский язык. Формулировки упрощай: вместо Deep-probe degraded пиши по-человечески, например Глубокая диагностика — ограничена, Причина: отсутствует доступ operator.read. В блоке Интеграции обязательно перечисляй каждую подтверждённую интеграцию отдельной строкой и не сокращай этот блок. Показывай как минимум: Telegram, OpenAI, Bitrix portal, Bitrix OAuth, Todoist, WHOOP, WAZZUP, WAZZUP_WEBHOOK_FORWARD, WEBHOOK, Web Search provider, а также другие подтверждённые интеграции, если они есть. Формат строки: название — статус. Если есть причина, выводи её отдельной строкой ниже. Для Bitrix пиши по-человечески: портал доступен, авторизация работает. Для незаведённых интеграций используй Не настроено. В блоке Планировщик по каждой задаче показывай: название, статус, последний запуск, доставка, ошибок подряд; если конкретных данных нет, не выдумывай их. В блоке Риски и техдолг оставляй только короткие управленческие формулировки без технического мусора. В конце обязательно делай сильный блок Итог: система стабильна или есть проблемы, есть ли критические проблемы, есть ли незначительные деградации, что требует плановой донастройки. Не перегружай эмодзи, не используй ASCII-таблицы и не превращай текст в полотно. Отчёт должен читаться за 5-10 секунд. Не выдавай API OK за пользовательский сценарий OK: статус интеграции, статус навыка и статус пользовательской возможности интерпретируй отдельно. Для web search отдельно различай провайдер поиска, навык поиска и Web search для Ларисы. Активной проблемой считай только текущий или неустранённый сбой. Если после ошибки уже есть более свежий успешный запуск, это не активная поломка, а наблюдение. Если свежий run ещё running, не объявляй старый error активной проблемой до завершения текущего run. Все времена указывай в Europe/Moscow.}"
MODE="${1:-inspect}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

health_description_b64="$(printf '%s' "$HEALTH_DESCRIPTION" | base64 | tr -d '\n')"
health_message_b64="$(printf '%s' "$HEALTH_MESSAGE" | base64 | tr -d '\n')"
status_description_b64="$(printf '%s' "$STATUS_DESCRIPTION" | base64 | tr -d '\n')"
status_message_b64="$(printf '%s' "$STATUS_MESSAGE" | base64 | tr -d '\n')"

remote_script=$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow

openclaw_dir='${OPENCLAW_DIR}'
node_bin='${OPENCLAW_NODE}'
runner='${OPENCLAW_RUNNER}'
compile_cache_dir='${OPENCLAW_COMPILE_CACHE_DIR}'
no_respawn='${OPENCLAW_NO_RESPAWN}'
health_name='${HEALTH_JOB_NAME}'
status_name='${STATUS_JOB_NAME}'
health_cron='${HEALTH_CRON_EXPR}'
status_cron='${STATUS_CRON_EXPR}'
health_delivery_mode='${HEALTH_DELIVERY_MODE}'
status_delivery_mode='${STATUS_DELIVERY_MODE}'
cron_tz='${CRON_TZ}'
mode='${MODE}'
cli_attempts='${OPENCLAW_CLI_ATTEMPTS}'
cli_retry_sleep='${OPENCLAW_CLI_RETRY_SLEEP}'
health_description="\$(printf '%s' '${health_description_b64}' | base64 -d)"
health_message="\$(printf '%s' '${health_message_b64}' | base64 -d)"
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
mkdir -p "\$compile_cache_dir"

run_openclaw() {
  if command -v openclaw >/dev/null 2>&1; then
    NODE_COMPILE_CACHE="\$compile_cache_dir" OPENCLAW_NO_RESPAWN="\$no_respawn" OPENCLAW_RUNNER_LOG=0 openclaw "\$@"
    return \$?
  fi
  if [ -f dist/entry.js ]; then
    NODE_COMPILE_CACHE="\$compile_cache_dir" OPENCLAW_NO_RESPAWN="\$no_respawn" OPENCLAW_RUNNER_LOG=0 "\$node_bin" dist/entry.js "\$@"
    return \$?
  fi
  NODE_COMPILE_CACHE="\$compile_cache_dir" OPENCLAW_NO_RESPAWN="\$no_respawn" OPENCLAW_RUNNER_LOG=0 "\$node_bin" "\$runner" "\$@"
}

extract_json() {
  sed -n '/^[[:space:]]*{/,\$p'
}

load_jobs_json() {
  local raw json attempt
  for attempt in \$(seq 1 "\$cli_attempts"); do
    raw="\$(run_openclaw cron list --all --json 2>&1 || true)"
    json="\$(printf '%s\n' "\$raw" | extract_json)"
    if [ -n "\$json" ]; then
      printf '%s\n' "\$json"
      return 0
    fi
    if [ "\$attempt" -lt "\$cli_attempts" ]; then
      echo "WARN: cron list вернул не-JSON (attempt=\${attempt}/\${cli_attempts}), повтор через \${cli_retry_sleep}s" >&2
      printf '%s\n' "\$raw" >&2
      sleep "\$cli_retry_sleep"
    fi
  done
  echo "ОШИБКА: не удалось выделить JSON из вывода cron list" >&2
  printf '%s\n' "\$raw" >&2
  return 1
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
health_edit_cmd=(
  cron edit "\$health_id"
  --enable
  --cron "\$health_cron"
  --tz "\$cron_tz"
  --message "\$health_message"
  --description "\$health_description"
)
if [ "\$health_delivery_mode" = "none" ]; then
  health_edit_cmd+=(--no-deliver)
else
  health_edit_cmd+=(--announce)
fi
run_openclaw "\${health_edit_cmd[@]}" >/tmp/openclaw_health_schedule_edit.json
sed -n '/^[[:space:]]*{/,\$p' /tmp/openclaw_health_schedule_edit.json || true

jobs_json="\$(load_jobs_json)"
status_id="\$(pick_job_id_by_name "\$jobs_json" "\$status_name")"

if [ -n "\$status_id" ]; then
  echo "Обновляю существующий status job: \$status_id -> '\$status_cron' (\$cron_tz)"
  status_edit_cmd=(
    cron edit "\$status_id"
    --enable
    --cron "\$status_cron"
    --tz "\$cron_tz"
    --message "\$status_message"
    --description "\$status_description"
  )
  if [ "\$status_delivery_mode" = "none" ]; then
    status_edit_cmd+=(--no-deliver)
  else
    status_edit_cmd+=(--announce)
  fi
  run_openclaw "\${status_edit_cmd[@]}" >/tmp/openclaw_status_schedule_edit.json
  sed -n '/^[[:space:]]*{/,\$p' /tmp/openclaw_status_schedule_edit.json || true
else
  echo "Создаю status job '\$status_name' на '\$status_cron' (\$cron_tz)"
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

  if [ "\$status_delivery_mode" = "none" ]; then
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
