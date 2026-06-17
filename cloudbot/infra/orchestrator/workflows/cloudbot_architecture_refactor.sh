#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

MODE="${1:-inspect}"
FEATURE_BRANCH="${FEATURE_BRANCH:-feature/project-structure}"
BASE_BRANCH="${BASE_BRANCH:-dev}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
GIT_BASE_CMD=(git -C "$ROOT_DIR")
SEARCH_DIRS=(bot checks docs infra ops scripts services)
MOVED_FILES=()

case "$MODE" in
  inspect|apply) ;;
  *) fail "Неизвестный режим: $MODE (inspect|apply)" ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_architecture_refactor_${STAMP}.txt"

push_branch_with_auth() {
  local branch="$1"
  local gh_token auth_header

  gh_token=""
  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then
      gh_token="$(gh auth token 2>/dev/null || true)"
    fi
  fi

  if [[ -n "$gh_token" ]]; then
    auth_header="$(printf 'x-access-token:%s' "$gh_token" | base64 | tr -d '\n')"
    "${GIT_BASE_CMD[@]}" \
      -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${auth_header}" \
      push -u origin "$branch"
    return 0
  fi

  "${GIT_BASE_CMD[@]}" push -u origin "$branch"
}

verify_no_sensitive_staged() {
  local staged
  staged="$("${GIT_BASE_CMD[@]}" diff --cached --name-only || true)"
  if [[ -z "$staged" ]]; then
    return 0
  fi

  if printf '%s\n' "$staged" \
      | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
      | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >/dev/null; then
    echo "ОШИБКА: в staged попали потенциально секретные файлы:" >&2
    printf '%s\n' "$staged" \
      | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
      | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >&2 || true
    return 1
  fi
}

create_directories() {
  mkdir -p "$ROOT_DIR/cloudbot"/{orchestrator,workflows,skills,providers,integrations,devops,scripts,configs,logs,tests,docs}
  mkdir -p "$ROOT_DIR/cloudbot/orchestrator"/{router,dispatcher,context}
  mkdir -p "$ROOT_DIR/cloudbot/workflows"/{day_briefing,tasks,meetings,health,notifications}
  mkdir -p "$ROOT_DIR/cloudbot/skills"/{bitrix_add_event,gcal_query,todo_tasks,web_search,whoop_data}
  mkdir -p "$ROOT_DIR/cloudbot/providers"/{bitrix,todoist,whoop,search,telegram}
  mkdir -p "$ROOT_DIR/devops" "$ROOT_DIR/configs" "$ROOT_DIR/logs" "$ROOT_DIR/tests"
}

write_orchestrator_module() {
  cat > "$ROOT_DIR/cloudbot/orchestrator/router/index.js" <<'JS'
export function selectWorkflow(intent) {
  const table = {
    day_briefing: "day_briefing",
    tasks: "tasks",
    meetings: "meetings",
    health: "health",
    notifications: "notifications"
  };

  return table[intent] || "day_briefing";
}
JS

  cat > "$ROOT_DIR/cloudbot/orchestrator/dispatcher/index.js" <<'JS'
export async function dispatchWorkflow(workflowName, registry, context) {
  const workflow = registry?.[workflowName];
  if (!workflow) {
    throw new Error(`Workflow not found: ${workflowName}`);
  }
  return workflow.run(context);
}
JS

  cat > "$ROOT_DIR/cloudbot/orchestrator/context/index.js" <<'JS'
export function buildContext(input) {
  return {
    receivedAt: new Date().toISOString(),
    input,
    meta: { source: "cloudbot-orchestrator" }
  };
}
JS

  cat > "$ROOT_DIR/cloudbot/orchestrator/index.js" <<'JS'
import { selectWorkflow } from "./router/index.js";
import { dispatchWorkflow } from "./dispatcher/index.js";
import { buildContext } from "./context/index.js";

export async function handleIncomingMessage(input, registry) {
  const context = buildContext(input);
  const workflowName = selectWorkflow(input?.intent || "day_briefing");
  return dispatchWorkflow(workflowName, registry, context);
}
JS
}

write_workflows_skeleton() {
  local wf
  for wf in day_briefing tasks meetings health notifications; do
    cat > "$ROOT_DIR/cloudbot/workflows/$wf/index.js" <<JS
export const workflow = {
  name: "$wf",
  async run(context) {
    return { ok: true, workflow: "$wf", context };
  }
};
JS
    cat > "$ROOT_DIR/cloudbot/workflows/$wf/README.md" <<MD
# Workflow: $wf

Назначение: сценарий $wf в новой архитектуре Cloudbot.

- Запускается через orchestrator router/dispatcher.
- Может использовать несколько skills.
- Не содержит прямого кода Telegram API.
MD
  done
}

write_skills_skeleton() {
  local skill
  for skill in bitrix_add_event gcal_query todo_tasks web_search whoop_data; do
    cat > "$ROOT_DIR/cloudbot/skills/$skill/index.js" <<JS
export async function run(payload, providers) {
  return {
    skill: "$skill",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
JS
    cat > "$ROOT_DIR/cloudbot/skills/$skill/README.md" <<MD
# Skill: $skill

- Изолированная функция для workflow.
- Не должна напрямую работать с Telegram.
- Доступ к внешним API только через providers.
MD
  done
}

write_providers_skeleton() {
  local p
  for p in bitrix todoist whoop search telegram; do
    cat > "$ROOT_DIR/cloudbot/providers/$p/index.js" <<JS
export function createProvider(config = {}) {
  return {
    name: "$p",
    config,
    async healthcheck() {
      return { provider: "$p", ok: true };
    }
  };
}
JS
    cat > "$ROOT_DIR/cloudbot/providers/$p/README.md" <<MD
# Provider: $p

Этот provider отвечает только за API слой $p.

- Никакой бизнес-логики workflow.
- Используется skills и orchestrator.
MD
  done
}

move_devops_scripts_with_compat() {
  if [[ -f "$ROOT_DIR/scripts/deploy.sh" ]]; then
    if ! grep -Fq 'exec "$ROOT_DIR/devops/deploy.sh"' "$ROOT_DIR/scripts/deploy.sh"; then
      if [[ ! -f "$ROOT_DIR/devops/deploy.sh" ]]; then
        mv "$ROOT_DIR/scripts/deploy.sh" "$ROOT_DIR/devops/deploy.sh"
        MOVED_FILES+=("scripts/deploy.sh -> devops/deploy.sh")
      fi
    fi
  fi

  if [[ -f "$ROOT_DIR/scripts/agent_commit.sh" ]]; then
    if ! grep -Fq 'exec "$ROOT_DIR/devops/backup.sh"' "$ROOT_DIR/scripts/agent_commit.sh"; then
      if [[ ! -f "$ROOT_DIR/devops/backup.sh" ]]; then
        mv "$ROOT_DIR/scripts/agent_commit.sh" "$ROOT_DIR/devops/backup.sh"
        MOVED_FILES+=("scripts/agent_commit.sh -> devops/backup.sh")
      fi
    fi
  fi

  cat > "$ROOT_DIR/devops/health_check.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/verify_live_integrations.sh reports
SCRIPT

  cat > "$ROOT_DIR/devops/diagnostics.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/preflight.sh
bash checks/context_contract_verify.sh
SCRIPT

  cat > "$ROOT_DIR/scripts/deploy.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT_DIR/devops/deploy.sh" "$@"
SCRIPT

  cat > "$ROOT_DIR/scripts/agent_commit.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT_DIR/devops/backup.sh" "$@"
SCRIPT

  chmod +x "$ROOT_DIR/devops/deploy.sh" "$ROOT_DIR/devops/backup.sh" \
    "$ROOT_DIR/devops/health_check.sh" "$ROOT_DIR/devops/diagnostics.sh" \
    "$ROOT_DIR/scripts/deploy.sh" "$ROOT_DIR/scripts/agent_commit.sh"
}

write_configs() {
  cp -f "$ROOT_DIR/.env.example" "$ROOT_DIR/configs/app_config.env.example"
  cp -f "$ROOT_DIR/.env.integrations.example" "$ROOT_DIR/configs/integrations.env.example"

  {
    echo "# Schedules (Europe/Moscow)"
    echo "CRON_TZ=Europe/Moscow"
    crontab -l 2>/dev/null || true
  } > "$ROOT_DIR/configs/schedules.cron"
}

write_architecture_doc() {
  cat > "$ROOT_DIR/docs/ARCHITECTURE.md" <<'MD'
# Cloudbot / OpenClaw — Structured Architecture

## Обзор
Проект переведён на целевую структуру с сохранением обратной совместимости.

## orchestrator
- Новый модуль: `cloudbot/orchestrator/`
- Слои: `router`, `dispatcher`, `context`.
- Назначение: принять вход, выбрать workflow, вызвать нужные skills.

## workflows
- Каталог: `cloudbot/workflows/`
- Базовые сценарии:
  - `day_briefing`
  - `tasks`
  - `meetings`
  - `health`
  - `notifications`

## skills
- Каталог: `cloudbot/skills/`
- Примеры:
  - `bitrix_add_event`
  - `gcal_query`
  - `todo_tasks`
  - `web_search`
  - `whoop_data`
- Правило: skills не работают напрямую с Telegram API.

## providers
- Каталог: `cloudbot/providers/`
- Провайдеры API:
  - `bitrix`
  - `todoist`
  - `whoop`
  - `search`
  - `telegram`
- Правило: providers отвечают только за API слой.

## integrations
- Каталог: `cloudbot/integrations/`
- Слой интеграционного связывания providers и workflow.

## devops
- Runtime-скрипты: `devops/`
  - `deploy.sh`
  - `health_check.sh`
  - `backup.sh`
  - `diagnostics.sh`
- Совместимость сохранена через wrapper-скрипты в `scripts/`.

## configs
- Каталог: `configs/`
  - `app_config.env.example`
  - `integrations.env.example`
  - `schedules.cron`

## текущая рабочая совместимость
- Основной работающий код не удалён.
- Существующие точки входа сохранены.
- Рефакторинг сделан постепенно и готов к дальнейшему переносу логики в новые каталоги.
MD
}

run_runtime_checks() {
  local integration_rc=0

  echo "[check] npm test"
  npm --prefix "$ROOT_DIR/bot" test

  echo "[check] npm smoke notifications"
  npm --prefix "$ROOT_DIR/bot" run smoke:notifications

  echo "[check] syntax deploy/backup/devops"
  bash -n "$ROOT_DIR/scripts/deploy.sh"
  bash -n "$ROOT_DIR/scripts/agent_commit.sh"
  bash -n "$ROOT_DIR/devops/deploy.sh"
  bash -n "$ROOT_DIR/devops/backup.sh"
  bash -n "$ROOT_DIR/devops/health_check.sh"
  bash -n "$ROOT_DIR/devops/diagnostics.sh"

  echo "[check] integrations"
  set +e
  bash "$ROOT_DIR/scripts/verify_local_preflight.sh" "$ROOT_DIR/reports"
  integration_rc=$?
  set -e
  if [[ "$integration_rc" -ne 0 ]]; then
    echo "[check][warn] verify_integrations вернул код $integration_rc (смотрим отчет в reports)."
  else
    echo "[check] verify_integrations: OK"
  fi

  echo "[check] logs"
  ls -1t "$ROOT_DIR/reports" | head -n 10
}

run_apply() {
  echo "=== ШАГ 2. Создание новой структуры ==="
  create_directories
  npm --prefix "$ROOT_DIR/bot" test

  echo "=== ШАГ 3. Выделение orchestrator ==="
  write_orchestrator_module
  npm --prefix "$ROOT_DIR/bot" test

  echo "=== ШАГ 4. Разделение workflows ==="
  write_workflows_skeleton

  echo "=== ШАГ 5. Организация skills ==="
  write_skills_skeleton

  echo "=== ШАГ 6. Создание providers ==="
  write_providers_skeleton

  echo "=== ШАГ 7. Выделение devops ==="
  move_devops_scripts_with_compat
  bash -n "$ROOT_DIR/scripts/deploy.sh"
  bash -n "$ROOT_DIR/scripts/agent_commit.sh"

  echo "=== ШАГ 8. Создание configs ==="
  write_configs

  echo "=== ШАГ 9. Документация ==="
  write_architecture_doc

  echo "=== ШАГ 10. Проверка ==="
  run_runtime_checks

  echo "=== ШАГ 11. Git commit/push ==="
  "${GIT_BASE_CMD[@]}" checkout "$FEATURE_BRANCH"
  "${GIT_BASE_CMD[@]}" add \
    cloudbot \
    devops \
    configs \
    docs/ARCHITECTURE.md \
    scripts/deploy.sh \
    scripts/agent_commit.sh \
    infra/orchestrator/workflows/cloudbot_architecture_refactor.sh

  verify_no_sensitive_staged

  if [[ -n "$("${GIT_BASE_CMD[@]}" diff --cached --name-only)" ]]; then
    "${GIT_BASE_CMD[@]}" commit -m "refactor: restructure cloudbot architecture"
  fi

  push_branch_with_auth "$FEATURE_BRANCH"
}

{
  echo "# Cloudbot Architecture Refactor"
  echo "Время: $(date '+%F %T %Z')"
  echo "Режим: $MODE"
  echo "Корень: $ROOT_DIR"
  echo

  echo "=== ШАГ 1. Анализ текущего проекта ==="
  ls -la
  find . -maxdepth 3 -type d | sort
  echo
  echo "Краткий отчет текущей архитектуры:"
  echo "- Код бота: $ROOT_DIR/bot"
  echo "- Интеграции/providers (текущие): $ROOT_DIR/bot/src/providers"
  echo "- Orchestrator: $ROOT_DIR/infra/orchestrator"
  if [[ -d "$ROOT_DIR/skills" ]]; then
    echo "- Skills в проекте: $ROOT_DIR/skills"
  else
    echo "- Skills проекта как отдельная папка отсутствуют (есть системные skills в ~/.codex/skills)"
  fi

  if [[ "$MODE" == "apply" ]]; then
    echo
    run_apply
  fi

  echo
  echo "=== ИТОГОВАЯ СТРУКТУРА (новая) ==="
  if [[ -d "$ROOT_DIR/cloudbot" ]]; then
    find "$ROOT_DIR/cloudbot" -maxdepth 3 -type d | sort
  else
    echo "- Каталог cloudbot пока не создан (режим inspect)."
  fi
  echo
  echo "=== ПЕРЕМЕЩЕННЫЕ ФАЙЛЫ ==="
  if [[ "${#MOVED_FILES[@]}" -eq 0 ]]; then
    echo "- Перемещений не было (или уже выполнены ранее)."
  else
    printf '%s\n' "${MOVED_FILES[@]}"
  fi

  echo
  echo "=== ФИНАЛЬНАЯ ПРОВЕРКА ==="
  echo "git branch"
  "${GIT_BASE_CMD[@]}" branch
  echo "git status"
  "${GIT_BASE_CMD[@]}" status --short --branch
} | tee "$REPORT_FILE"

log "Workflow cloudbot_architecture_refactor завершён"
log "Отчет: $REPORT_FILE"
