#!/usr/bin/env bash
set -euo pipefail

TZ=Europe/Moscow
export TZ

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SENTRY_API="$CODEX_HOME/skills/sentry/scripts/sentry_api.py"
PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"
ENV_FILE="${ENV_FILE:-.env.integrations}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

status=0

ok() { printf "[OK] %s\n" "$1"; }
warn() { printf "[WARN] %s\n" "$1"; status=1; }

check_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    ok "Команда найдена: $name"
  else
    warn "Команда не найдена: $name"
  fi
}

check_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    ok "Файл найден: $path"
  else
    warn "Файл не найден: $path"
  fi
}

printf "=== ПРЕДПРОВЕРКА (%s) ===\n" "$(date '+%F %T %Z')"

check_cmd bash
check_cmd python3
check_cmd node
check_cmd npm
check_cmd npx
check_cmd gh

check_file "$SENTRY_API"
check_file "$PWCLI"

for s in gh-fix-ci gh-address-comments sentry playwright openai-docs security-best-practices security-threat-model notion-spec-to-implementation; do
  check_file "$CODEX_HOME/skills/$s/SKILL.md"
done
check_file "$CODEX_HOME/skills/.system/skill-creator/SKILL.md"

for v in SENTRY_AUTH_TOKEN SENTRY_ORG SENTRY_PROJECT OPENAI_API_KEY NOTION_TOKEN; do
  if [[ -n "${!v:-}" ]]; then
    ok "Переменная задана: $v"
  else
    warn "Переменная не задана: $v"
  fi
done

if [[ $status -eq 0 ]]; then
  printf "\nИтог: ОК (базовая готовность подтверждена)\n"
else
  printf "\nИтог: есть проблемы (см. WARN выше)\n"
fi

exit "$status"
