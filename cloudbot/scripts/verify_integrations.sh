#!/usr/bin/env bash
set -euo pipefail

TZ=Europe/Moscow
export TZ

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SENTRY_API="$CODEX_HOME/skills/sentry/scripts/sentry_api.py"
ENV_FILE="${ENV_FILE:-.env.integrations}"
VERIFY_SCOPE="${VERIFY_SCOPE:-local}"

case "$VERIFY_SCOPE" in
  local|live) ;;
  *)
    echo "Неизвестный VERIFY_SCOPE: $VERIFY_SCOPE (доступно: local, live)" >&2
    exit 2
    ;;
esac

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
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

skip() {
  printf "[SKIP] %s\n" "$1" | tee -a "$REPORT_FILE"
}

bad() {
  printf "[ПРОБЛЕМА] %s\n" "$1" | tee -a "$REPORT_FILE"
  has_problem=1
}

soft_bad() {
  if [[ "$VERIFY_SCOPE" != "live" ]]; then
    skip "$1"
  elif [[ "${DRY_RUN:-0}" == "1" ]]; then
    skip "$1"
  else
    bad "$1"
  fi
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

run_wazzup_check() {
  local base_url endpoint body_file http_code curl_rc

  base_url="${WAZZUP_API_BASE_URL:-https://api.wazzup24.com}"
  endpoint="${WAZZUP_API_CHECK_URL:-${base_url%/}/v3/channels}"
  body_file="$(mktemp)"

  echo "WAZZUP endpoint: ${endpoint}"

  set +e
  http_code="$(curl -sS --max-time 20 -o "$body_file" -w '%{http_code}' \
    -H "Authorization: Bearer ${WAZZUP_API_KEY}" \
    -H "Content-Type: application/json" \
    "$endpoint")"
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    rm -f "$body_file"
    echo "curl_rc=${curl_rc}"
    return 1
  fi

  echo "http_code=${http_code}"
  if [[ "$http_code" != "200" ]]; then
    sed -n '1,40p' "$body_file" || true
    rm -f "$body_file"
    return 1
  fi

  if command -v jq >/dev/null 2>&1; then
    jq '.[0]? // .' "$body_file" 2>/dev/null | sed -n '1,20p' || sed -n '1,20p' "$body_file"
  else
    sed -n '1,20p' "$body_file"
  fi

  rm -f "$body_file"
}

printf "Время проверки: %s\n" "$(date '+%F %T %Z')" >"$REPORT_FILE"
printf "Часовой пояс: Europe/Moscow\n" >>"$REPORT_FILE"
printf "Контур проверки: %s\n" "$VERIFY_SCOPE" >>"$REPORT_FILE"

section "Сервисы и CLI"
run_cmd "Node доступен" node -v
run_cmd "npm доступен" npm -v
if command -v gh >/dev/null 2>&1; then
  run_cmd "gh доступен" gh --version
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    if gh auth status >>"$REPORT_FILE" 2>&1; then
      ok "GitHub авторизация активна"
    else
      skip "GitHub авторизация не активна: dry-run не требует live-gh"
    fi
  else
    run_cmd "GitHub авторизация активна" gh auth status
  fi
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
  soft_bad "OPENAI_API_KEY не задан"
fi

section "Notion"
if [[ -n "${NOTION_TOKEN:-}" ]]; then
  run_cmd "NOTION_TOKEN задан" /usr/bin/env bash -lc '[[ -n "${NOTION_TOKEN:-}" ]]'
else
  soft_bad "NOTION_TOKEN не задан"
fi

section "Telegram"
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && { [[ -n "${TELEGRAM_CHAT_ID:-}" ]] || [[ -n "${TELEGRAM_TARGETS:-}" ]]; }; then
  run_cmd "TELEGRAM_BOT_TOKEN задан" /usr/bin/env bash -lc '[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]'
  if [[ -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    run_cmd "TELEGRAM_CHAT_ID задан" /usr/bin/env bash -lc '[[ -n "${TELEGRAM_CHAT_ID:-}" ]]'
  else
    ok "TELEGRAM_CHAT_ID не задан, используется TELEGRAM_TARGETS"
  fi
  if [[ -n "${TELEGRAM_TARGETS:-}" ]]; then
    run_cmd "TELEGRAM_TARGETS задан" /usr/bin/env bash -lc '[[ -n "${TELEGRAM_TARGETS:-}" ]]'
  else
    ok "TELEGRAM_TARGETS не задан, используется только TELEGRAM_CHAT_ID"
  fi
else
  soft_bad "TELEGRAM_BOT_TOKEN и Telegram target не заданы (TELEGRAM_CHAT_ID или TELEGRAM_TARGETS)"
fi

section "WAZZUP"
if [[ -n "${WAZZUP_API_KEY:-}" ]]; then
  run_cmd "WAZZUP_API_KEY задан" /usr/bin/env bash -lc '[[ -n "${WAZZUP_API_KEY:-}" ]]'
  if [[ -n "${WAZZUP_API_BASE_URL:-}" ]]; then
    ok "WAZZUP_API_BASE_URL задан"
  else
    ok "WAZZUP_API_BASE_URL не задан, используется https://api.wazzup24.com"
  fi
  run_cmd "WAZZUP API channels" run_wazzup_check
else
  ok "WAZZUP_API_KEY не задан: live-проверка пропущена"
fi

section "Sentry"
if [[ -n "${SENTRY_AUTH_TOKEN:-}" && -n "${SENTRY_ORG:-}" && -n "${SENTRY_PROJECT:-}" ]]; then
  if [[ -f "$SENTRY_API" ]]; then
    run_cmd "Sentry API script доступен" test -f "$SENTRY_API"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      if python3 "$SENTRY_API" list-issues --org "$SENTRY_ORG" --project "$SENTRY_PROJECT" --environment prod --time-range 24h --limit 3 >>"$REPORT_FILE" 2>&1; then
        ok "Sentry: чтение issues за 24h"
      else
        skip "Sentry: live-проверка issues пропущена в dry-run"
      fi
    else
      run_cmd "Sentry: чтение issues за 24h" python3 "$SENTRY_API" list-issues --org "$SENTRY_ORG" --project "$SENTRY_PROJECT" --environment prod --time-range 24h --limit 3
    fi
  else
    soft_bad "Не найден $SENTRY_API"
  fi
else
  soft_bad "Sentry переменные не заполнены (нужны SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT)"
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
