#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

MODE="${1:-inspect}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
GIT_BASE_CMD=(git -C "$ROOT_DIR")
SEARCH_DIRS=(bot checks docs infra ops scripts services)
CRON_TZ_LINE="CRON_TZ=Europe/Moscow"
CRON_LINE="0 3 * * * cd '$ROOT_DIR' && ./scripts/agent_commit.sh >> reports/backup.log 2>&1"

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_repo_setup_${STAMP}.txt"

list_sensitive_tracked() {
  "${GIT_BASE_CMD[@]}" ls-files \
    | rg '(^|/)\.env($|[^/]*$)|\.key$|\.pem$|\.token$|\.secret$' \
    | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' || true
}

verify_no_sensitive_staged() {
  local staged
  staged="$("${GIT_BASE_CMD[@]}" diff --cached --name-only || true)"
  if [[ -z "$staged" ]]; then
    return 0
  fi

  if printf '%s\n' "$staged" \
    | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$' \
    | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >/dev/null; then
    echo "ОШИБКА: в staged попали потенциально секретные файлы:" >&2
    printf '%s\n' "$staged" \
      | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$' \
      | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >&2 || true
    return 1
  fi
}

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

write_deploy_script() {
  cat > "$ROOT_DIR/scripts/deploy.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BRANCH="${1:-${DEPLOY_BRANCH:-}}"

cd "$ROOT_DIR"

current_branch="$(git branch --show-current)"
if [[ -z "$TARGET_BRANCH" ]]; then
    if [[ -z "$current_branch" ]]; then
        echo "ОШИБКА: не удалось определить branch для deploy. Передай DEPLOY_BRANCH или первый аргумент." >&2
        exit 1
    fi
    TARGET_BRANCH="$current_branch"
fi

if [[ -n "$(git status --porcelain)" && "$current_branch" != "$TARGET_BRANCH" ]]; then
    echo "ОШИБКА: рабочее дерево грязное, нельзя переключать deploy на ветку $TARGET_BRANCH." >&2
    exit 1
fi

echo "Updating repository from branch: $TARGET_BRANCH"
git fetch origin "$TARGET_BRANCH"

if [[ "$current_branch" != "$TARGET_BRANCH" ]]; then
    git checkout "$TARGET_BRANCH"
fi

git pull --ff-only origin "$TARGET_BRANCH"

echo "Restarting services..."

if command -v docker >/dev/null 2>&1; then
    docker compose down || true
    docker compose up -d --build
fi

echo "Deploy complete."
SCRIPT
  chmod +x "$ROOT_DIR/scripts/deploy.sh"
}

write_agent_commit_script() {
  cat > "$ROOT_DIR/scripts/agent_commit.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BRANCH="${1:-${GIT_PUSH_BRANCH:-}}"
ALLOW_MAIN_PUSH="${ALLOW_MAIN_PUSH:-0}"

cd "$ROOT_DIR"

current_branch="$(git branch --show-current)"
if [[ -z "$current_branch" ]]; then
    echo "ОШИБКА: agent_commit.sh нельзя запускать из detached HEAD." >&2
    exit 1
fi

if [[ -z "$TARGET_BRANCH" ]]; then
    TARGET_BRANCH="$current_branch"
fi

if [[ "$TARGET_BRANCH" != "$current_branch" ]]; then
    echo "ОШИБКА: agent_commit.sh не будет пушить в $TARGET_BRANCH из текущей ветки $current_branch." >&2
    exit 1
fi

if [[ "$TARGET_BRANCH" == "main" && "$ALLOW_MAIN_PUSH" != "1" ]]; then
    echo "ОШИБКА: прямой push в main заблокирован. Используй feature/dev ветку." >&2
    exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    echo "ОШИБКА: remote origin не настроен, backup commit отменён." >&2
    exit 1
fi

if ! git ls-remote --exit-code origin >/dev/null 2>&1; then
    echo "ОШИБКА: origin недоступен, backup commit отменён до создания локального commit." >&2
    exit 1
fi

git add .

if git diff --cached --quiet; then
    echo "Нет изменений для backup commit."
    exit 0
fi

git commit -m "backup: snapshot $(date '+%Y-%m-%d %H:%M %Z')"
git push -u origin "$TARGET_BRANCH"
SCRIPT
  chmod +x "$ROOT_DIR/scripts/agent_commit.sh"
}

write_architecture_doc() {
  cat > "$ROOT_DIR/ARCHITECTURE.md" <<'MD'
# Cloudbot / OpenClaw Architecture

## orchestrator
- Оркестратор управляет запуском операций и стандартными workflow через `infra/orchestrator/run_workflow.sh`.
- Общие функции и окружение централизованы в `infra/orchestrator/lib.sh`.

## workflows
- Workflow в `infra/orchestrator/workflows/` покрывают ежедневные проверки, обновления, деплой и восстановление.
- Каждый workflow реализует пошаговый сценарий с отчетом в `reports/`.

## skills
- Skills расширяют поведение агента и задают стандартизированные процедуры выполнения задач.
- Используются для repeatable-операций: деплой, безопасность, интеграции, документация.

## providers
- Провайдеры в `bot/src/providers/` абстрагируют источники данных и интеграции.
- Основные источники: Bitrix, Todo/Todoist, внутренние источники и вспомогательные адаптеры.

## integrations
- Ключевые интеграции: Telegram, OpenAI, Bitrix, Todoist, WHOOP, Sentry, Notion.
- Проверки доступности и конфигурации выполняются скриптами в `scripts/` и `checks/`.

## search
- Поисковая логика подключается как отдельный провайдер/интеграция.
- Внешние API и ключи хранятся только в локальных env-файлах, не в git.

## telegram bot
- Telegram-бот в `bot/` является основным интерфейсом взаимодействия.
- Команды, расписания и уведомления реализованы в `bot/src/commands`, `bot/src/scheduler`, `bot/src/workflows`.

## devops
- Деплой и обслуживание автоматизируются через workflow и скрипты `scripts/deploy.sh`, `scripts/agent_commit.sh`.
- Backup изменений выполняется cron-задачей в 03:00 MSK.
- Отчеты и операционные логи сохраняются в `reports/`.
MD
}

write_codex_rules_doc() {
  cat > "$ROOT_DIR/CODEX_RULES.md" <<'MD'
# CODEX Rules

1. Никогда не коммитить `.env`.
2. Никогда не коммитить API-ключи.
3. Каноническая integration-ветка: `dev`.
4. Новые изменения делать в `feature/*` или `codex/feature/*` от актуального `dev`.
5. Не пушить `main` напрямую без отдельного решения.
6. `scripts/agent_commit.sh` не должен пушить branch, отличный от текущего checkout.
MD
}

ensure_dev_branch() {
  if "${GIT_BASE_CMD[@]}" show-ref --verify --quiet refs/heads/dev; then
    "${GIT_BASE_CMD[@]}" checkout dev
  else
    "${GIT_BASE_CMD[@]}" checkout -b dev
  fi
}

setup_backup_cron() {
  local existing new_block
  existing="$(crontab -l 2>/dev/null || true)"
  new_block="$existing"

  if ! printf '%s\n' "$new_block" | grep -Fqx "$CRON_TZ_LINE"; then
    if [[ -n "$new_block" ]]; then
      new_block="$CRON_TZ_LINE
$new_block"
    else
      new_block="$CRON_TZ_LINE"
    fi
  fi

  if ! printf '%s\n' "$new_block" | grep -Fqx "$CRON_LINE"; then
    new_block="$new_block
$CRON_LINE"
  fi

  printf '%s\n' "$new_block" | awk 'NF || prev {print} {prev=NF}' | crontab -
}

run_apply() {
  echo "=== ШАГ 2. Ветка dev ==="
  ensure_dev_branch
  push_branch_with_auth dev

  echo "=== ШАГ 3. deploy.sh ==="
  write_deploy_script

  echo "=== ШАГ 4. agent_commit.sh ==="
  write_agent_commit_script

  echo "=== ШАГ 5. Ежедневный backup (cron) ==="
  setup_backup_cron

  echo "=== ШАГ 6. ARCHITECTURE.md ==="
  write_architecture_doc

  echo "=== ШАГ 7. CODEX_RULES.md ==="
  write_codex_rules_doc

  echo "=== Коммит изменений ==="
  "${GIT_BASE_CMD[@]}" add \
    scripts/deploy.sh \
    scripts/agent_commit.sh \
    ARCHITECTURE.md \
    CODEX_RULES.md \
    infra/orchestrator/workflows/cloudbot_repo_setup.sh

  verify_no_sensitive_staged

  if [[ -n "$("${GIT_BASE_CMD[@]}" diff --cached --name-only)" ]]; then
    "${GIT_BASE_CMD[@]}" commit -m "Настройка GitHub-процесса, deploy и backup"
    push_branch_with_auth dev
  fi

  echo "=== Тестирование и проверка ==="
  bash -n "$ROOT_DIR/scripts/deploy.sh"
  bash -n "$ROOT_DIR/scripts/agent_commit.sh"
  bash -n "$ROOT_DIR/infra/orchestrator/workflows/cloudbot_repo_setup.sh"
  npm --prefix "$ROOT_DIR/bot" test

  echo "=== Проверка cron ==="
  crontab -l || true
}

{
  echo "# Cloudbot Repo Setup"
  echo "Время: $(date '+%F %T %Z')"
  echo "Режим: $MODE"
  echo "Корень: $ROOT_DIR"
  echo

  echo "=== ШАГ 1. Проверка утечки секретов ==="
  echo "grep -R \"API\" -n ."
  grep -R "API" -n "${SEARCH_DIRS[@]}" || true
  echo "grep -R \"TOKEN\" -n ."
  grep -R "TOKEN" -n "${SEARCH_DIRS[@]}" || true
  echo "grep -R \"SECRET\" -n ."
  grep -R "SECRET" -n "${SEARCH_DIRS[@]}" || true
  echo
  echo "Дополнительный поиск по ключевым словам:"
  rg -n '(API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY|BITRIX|WHOOP)' "${SEARCH_DIRS[@]}" || true
  echo
  echo "git ls-files"
  "${GIT_BASE_CMD[@]}" ls-files
  echo
  echo "Проверка отслеживаемых секретных файлов (.env/.key/.pem/.token/.secret):"
  tracked_sensitive="$(list_sensitive_tracked)"
  if [[ -n "$tracked_sensitive" ]]; then
    echo "ОБНАРУЖЕНЫ потенциально секретные файлы в git:"
    printf '%s\n' "$tracked_sensitive"
  else
    echo "ОК: секретные файлы в git не обнаружены."
  fi

  if [[ "$MODE" == "apply" ]]; then
    echo
    run_apply
  fi

  echo
  echo "=== Финальная проверка ==="
  echo "git branch"
  "${GIT_BASE_CMD[@]}" branch
  echo "ls scripts"
  ls "$ROOT_DIR/scripts"
  echo "git status"
  "${GIT_BASE_CMD[@]}" status --short --branch
} | tee "$REPORT_FILE"

log "Workflow cloudbot_repo_setup завершён"
log "Отчет: $REPORT_FILE"
