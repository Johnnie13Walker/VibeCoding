#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

MODE="${1:-inspect}"
REPO_NAME="${REPO_NAME:-cloudbot}"
REPO_URL="${REPO_URL:-}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
DEV_BRANCH="${DEV_BRANCH:-dev}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
GIT_BASE_CMD=(git -C "$ROOT_DIR")
SEARCH_DIRS=(bot checks docs infra ops scripts services)

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_github_migrate_${STAMP}.txt"

run_tree_l2() {
  if command -v tree >/dev/null 2>&1; then
    tree -L 2 \
      -I '.git|node_modules|venv|.venv|__pycache__|reports'
  else
    echo "tree не установлен, показываю аналог через find (глубина 2):"
    find . -maxdepth 2 -mindepth 1 \
      -not -path './.git*' \
      -not -path './node_modules*' \
      -not -path './venv*' \
      -not -path './.venv*' \
      -not -path './__pycache__*' \
      -not -path './reports*' | sort
  fi
}

collect_sensitive_candidates() {
  {
    find . -type f \( -name '.env' -o -name '.env.*' -o -name '*.key' -o -name '*.pem' -o -name '*.token' -o -name '*.secret' \) \
      -not -path './.git/*' \
      -not -path './node_modules/*' \
      -not -path './.venv/*' \
      -not -path './venv/*' \
      -not -path './reports/*' \
      -not -name '*.example' || true
    find . -type f -path './infra/happ-vpn.env' || true
  } | sed 's#^\./##' | sort -u
}

extract_env_names() {
  {
    rg -n --no-filename --no-messages '^[A-Z][A-Z0-9_]*=' .env* || true
    rg -n --no-filename --no-messages '(OPENAI_API_KEY|TELEGRAM_BOT_TOKEN|BITRIX_TOKEN|WHOOP_TOKEN|BRAVE_API_KEY|TODOIST|VPN|API_KEY|TOKEN|SECRET)' "${SEARCH_DIRS[@]}" || true
  } | sed -E 's/^([A-Z][A-Z0-9_]*)=.*/\1/' \
    | rg '^[A-Z][A-Z0-9_]*$' \
    | sort -u || true
}

write_gitignore() {
  local sensitive_file_list="$1"
  cat > "$ROOT_DIR/.gitignore" <<'GI'
.env
.env.*
!.env.example
!.env.integrations.example
*.key
*.pem
*.token
*.secret
node_modules
__pycache__
*.log
logs/
.cache
venv/
.idea
.vscode
reports/
GI

  if [[ -n "$sensitive_file_list" ]]; then
    printf '\n# Автодобавлено: потенциально чувствительные файлы\n' >> "$ROOT_DIR/.gitignore"
    while IFS= read -r p; do
      [[ -z "$p" ]] && continue
      [[ "$p" == ".gitignore" ]] && continue
      printf '%s\n' "$p" >> "$ROOT_DIR/.gitignore"
    done <<< "$sensitive_file_list"
  fi

  awk '!seen[$0]++' "$ROOT_DIR/.gitignore" > "$ROOT_DIR/.gitignore.tmp"
  mv "$ROOT_DIR/.gitignore.tmp" "$ROOT_DIR/.gitignore"
}

write_env_example() {
  local vars
  vars="$(extract_env_names)"
  {
    echo "# Шаблон переменных окружения (без значений)"
    echo "OPENAI_API_KEY="
    echo "TELEGRAM_BOT_TOKEN="
    echo "BITRIX_TOKEN="
    echo "WHOOP_TOKEN="
    echo "BRAVE_API_KEY="
    if [[ -n "$vars" ]]; then
      while IFS= read -r v; do
        [[ -z "$v" ]] && continue
        case "$v" in
          OPENAI_API_KEY|TELEGRAM_BOT_TOKEN|BITRIX_TOKEN|WHOOP_TOKEN|BRAVE_API_KEY) continue ;;
        esac
        echo "$v="
      done <<< "$vars"
    fi
  } | awk '!seen[$0]++' > "$ROOT_DIR/.env.example"
}

verify_no_sensitive_in_index() {
  local staged
  staged="$("${GIT_BASE_CMD[@]}" diff --cached --name-only || true)"
  if [[ -z "$staged" ]]; then
    return 0
  fi

  # Блокируем явные секретные файлы, но разрешаем env-шаблоны.
  if printf '%s\n' "$staged" | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
    | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >/dev/null; then
    echo "ОШИБКА: в staged попали потенциально чувствительные файлы:" >&2
    printf '%s\n' "$staged" \
      | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
      | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >&2 || true
    return 1
  fi

  # Ищем только высоковероятные секреты в содержимом diff.
  if "${GIT_BASE_CMD[@]}" diff --cached \
    | rg -n '(-----BEGIN [A-Z ]+PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}|(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["'"'"'][A-Za-z0-9_\-]{12,}["'"'"'])' >/dev/null; then
    echo "ОШИБКА: в staged diff обнаружены признаки секретов." >&2
    "${GIT_BASE_CMD[@]}" diff --cached \
      | rg -n '(-----BEGIN [A-Z ]+PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}|(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["'"'"'][A-Za-z0-9_\-]{12,}["'"'"'])' >&2 || true
    return 1
  fi
}

create_readme() {
  cat > "$ROOT_DIR/README.md" <<'MD'
# Cloudbot / OpenClaw

## Структура проекта
- `bot/` — код бота и прикладная логика.
- `checks/` — проверки и smoke/health скрипты.
- `infra/` — инфраструктура и orchestrator workflow.
- `ops/` — операционные утилиты.
- `scripts/` — вспомогательные скрипты.
- `services/` — сервисные модули.
- `reports/` — отчёты выполнения и диагностики.

## Запуск
1. Установить зависимости для используемых сервисов.
2. Скопировать шаблон переменных окружения в локальный env-файл.
3. Запускать операции через orchestrator:
   - `./infra/orchestrator/run_workflow.sh <workflow_name> [inspect|apply]`

## Переменные окружения
- Шаблон: `.env.example`
- Локальные секреты: `.env` и `.env.*` (не коммитятся)
MD
}

run_apply() {
  local sensitive_candidates
  sensitive_candidates="$(collect_sensitive_candidates)"

  write_gitignore "$sensitive_candidates"
  write_env_example
  create_readme

  if [[ ! -d "$ROOT_DIR/.git" ]]; then
    "${GIT_BASE_CMD[@]}" init
  fi

  "${GIT_BASE_CMD[@]}" add .
  verify_no_sensitive_in_index

  if "${GIT_BASE_CMD[@]}" rev-parse --verify HEAD >/dev/null 2>&1; then
    if [[ -n "$("${GIT_BASE_CMD[@]}" diff --cached --name-only)" ]]; then
      "${GIT_BASE_CMD[@]}" commit -m "Первичный коммит: Cloudbot без секретов"
    fi
  else
    "${GIT_BASE_CMD[@]}" commit -m "Первичный коммит: Cloudbot без секретов"
  fi

  "${GIT_BASE_CMD[@]}" branch -M "$DEFAULT_BRANCH"

  if "${GIT_BASE_CMD[@]}" remote get-url origin >/dev/null 2>&1; then
    if [[ -n "$REPO_URL" ]]; then
      "${GIT_BASE_CMD[@]}" remote set-url origin "$REPO_URL"
    fi
  else
    if [[ -n "$REPO_URL" ]]; then
      "${GIT_BASE_CMD[@]}" remote add origin "$REPO_URL"
    else
      (
        cd "$ROOT_DIR"
        gh repo create "$REPO_NAME" --private --source=. --remote=origin >/dev/null
      )
    fi
  fi

  "${GIT_BASE_CMD[@]}" push -u origin "$DEFAULT_BRANCH"

  if "${GIT_BASE_CMD[@]}" show-ref --verify --quiet "refs/heads/$DEV_BRANCH"; then
    "${GIT_BASE_CMD[@]}" checkout "$DEV_BRANCH"
  else
    "${GIT_BASE_CMD[@]}" checkout -b "$DEV_BRANCH"
  fi

  local repo_url
  repo_url="$("${GIT_BASE_CMD[@]}" remote get-url origin)"

  echo
  echo "=== ИТОГ ==="
  echo "remote=$repo_url"
  echo "branch=$("${GIT_BASE_CMD[@]}" branch --show-current)"
  echo "tracked_files_count=$("${GIT_BASE_CMD[@]}" ls-files | wc -l | tr -d ' ')"
  echo
  echo "--- Структура (уровень 2) ---"
  run_tree_l2
  echo
  echo "--- Файлы в git ---"
  "${GIT_BASE_CMD[@]}" ls-files
}

{
  echo "# Cloudbot GitHub Migration"
  echo "Время: $(date '+%F %T %Z')"
  echo "Режим: $MODE"
  echo "Корень: $ROOT_DIR"
  echo

  echo "=== ШАГ 1: Рабочая директория ==="
  pwd
  ls -la
  run_tree_l2

  echo
  echo "=== ШАГ 2: Скан потенциальных секретов ==="
  echo "grep -R \"API_KEY\" -n"
  grep -R "API_KEY" -n "${SEARCH_DIRS[@]}" || true
  echo "grep -R \"TOKEN\" -n"
  grep -R "TOKEN" -n "${SEARCH_DIRS[@]}" || true
  echo "grep -R \"SECRET\" -n"
  grep -R "SECRET" -n "${SEARCH_DIRS[@]}" || true
  echo
  echo "Потенциально чувствительные файлы:"
  collect_sensitive_candidates || true

  if [[ "$MODE" == "apply" ]]; then
    echo
    echo "=== ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ ==="
    run_apply

    echo
    echo "=== Проверка безопасности после push ==="
    if "${GIT_BASE_CMD[@]}" ls-files \
      | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
      | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >/dev/null; then
      echo "ОШИБКА: чувствительные файлы есть в индексе после push" >&2
      "${GIT_BASE_CMD[@]}" ls-files \
        | rg '(^|/)\.env($|[^/]*$)|(^|/).*\.key$|(^|/).*\.pem$|(^|/).*\.token$|(^|/).*\.secret$|^infra/happ-vpn\.env$' \
        | rg -v '(^|/)\.env\.example$|(^|/)\.env\.integrations\.example$' >&2 || true
      exit 1
    fi
    echo "Проверка пройдена: явные секретные файлы в git не обнаружены."
  fi
} | tee "$REPORT_FILE"

log "Workflow cloudbot_github_migrate завершён"
log "Отчет: $REPORT_FILE"
