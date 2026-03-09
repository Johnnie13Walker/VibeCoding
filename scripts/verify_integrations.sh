#!/usr/bin/env bash
set -euo pipefail

TZ=Europe/Moscow
export TZ

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SENTRY_API="$CODEX_HOME/skills/sentry/scripts/sentry_api.py"
ENV_FILE="${ENV_FILE:-.env.integrations}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

REPORT_DIR="${1:-./reports}"
mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_FILE="$REPORT_DIR/health_${STAMP}_MSK.txt"

has_problem=0

section() {
  printf "\n## %s\n" "$1" | tee -a "$REPORT_FILE"
}

ok() {
  printf "[OK] %s\n" "$1" | tee -a "$REPORT_FILE"
}

bad() {
  printf "[ПРОБЛЕМА] %s\n" "$1" | tee -a "$REPORT_FILE"
  has_problem=1
}

run_cmd() {
  local title="$1"
  shift
  if "$@" >>"$REPORT_FILE" 2>&1; then
    ok "$title"
  else
    bad "$title"
  fi
}

printf "Время проверки: %s\n" "$(date '+%F %T %Z')" >"$REPORT_FILE"
printf "Часовой пояс: Europe/Moscow\n" >>"$REPORT_FILE"

section "Сервисы и CLI"
run_cmd "Node доступен" node -v
run_cmd "npm доступен" npm -v
if command -v gh >/dev/null 2>&1; then
  run_cmd "gh доступен" gh --version
  run_cmd "GitHub авторизация активна" gh auth status
else
  bad "gh не установлен"
fi

section "Bot smoke (уведомления задач)"
run_cmd "Bot smoke test" /usr/bin/env bash -lc 'cd bot && npm test'
run_cmd "Bot smoke notifications" /usr/bin/env bash -lc 'cd bot && npm run smoke:notifications'
run_cmd "Bot jobs run-once (dry-run)" /usr/bin/env bash -lc 'cd bot && TELEGRAM_DRY_RUN=1 TELEGRAM_OWNER_ID="${TELEGRAM_OWNER_ID:-100500}" TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-700700}" npm run jobs:run-once'

section "OpenAI"
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  run_cmd "OPENAI_API_KEY задан" /usr/bin/env bash -lc '[[ -n "${OPENAI_API_KEY:-}" ]]'
else
  bad "OPENAI_API_KEY не задан"
fi

section "Notion"
if [[ -n "${NOTION_TOKEN:-}" ]]; then
  run_cmd "NOTION_TOKEN задан" /usr/bin/env bash -lc '[[ -n "${NOTION_TOKEN:-}" ]]'
else
  bad "NOTION_TOKEN не задан"
fi

section "Telegram"
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  run_cmd "TELEGRAM_BOT_TOKEN задан" /usr/bin/env bash -lc '[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]'
  run_cmd "TELEGRAM_CHAT_ID задан" /usr/bin/env bash -lc '[[ -n "${TELEGRAM_CHAT_ID:-}" ]]'
else
  bad "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы"
fi

section "Sentry"
if [[ -n "${SENTRY_AUTH_TOKEN:-}" && -n "${SENTRY_ORG:-}" && -n "${SENTRY_PROJECT:-}" ]]; then
  if [[ -f "$SENTRY_API" ]]; then
    run_cmd "Sentry API script доступен" test -f "$SENTRY_API"
    run_cmd "Sentry: чтение issues за 24h" python3 "$SENTRY_API" list-issues --org "$SENTRY_ORG" --project "$SENTRY_PROJECT" --environment prod --time-range 24h --limit 3
  else
    bad "Не найден $SENTRY_API"
  fi
else
  bad "Sentry переменные не заполнены (нужны SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT)"
fi

section "Проверка skill-файлов"
for s in gh-fix-ci gh-address-comments sentry playwright openai-docs security-best-practices security-threat-model notion-spec-to-implementation; do
  if [[ -f "$CODEX_HOME/skills/$s/SKILL.md" ]]; then
    ok "Найден skill: $s"
  else
    bad "Отсутствует skill: $s"
  fi
done
if [[ -f "$CODEX_HOME/skills/.system/skill-creator/SKILL.md" ]]; then
  ok "Найден системный skill: skill-creator"
else
  bad "Отсутствует системный skill: skill-creator"
fi

section "Итог"
if [[ "$has_problem" -eq 0 ]]; then
  printf "ОК\n" | tee -a "$REPORT_FILE"
else
  printf "есть проблемы\n" | tee -a "$REPORT_FILE"
fi

printf "\nОтчет: %s\n" "$REPORT_FILE"
exit "$has_problem"
