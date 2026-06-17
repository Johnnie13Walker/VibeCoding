#!/usr/bin/env bash
set -euo pipefail

TZ=Europe/Moscow
export TZ

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CLOUDBOT_ENGINEER_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "$REPO_ROOT"

echo "== Лариса: финализация интеграций ($(date '+%F %T %Z')) =="

if [[ ! -f ".env.integrations" ]]; then
  ./scripts/bootstrap_env.sh
fi

echo "Шаг 1/4: Проверка gh"
if command -v gh >/dev/null 2>&1; then
  echo "[OK] gh найден"
else
  echo "[ПРОБЛЕМА] gh не найден"
  exit 1
fi

echo "Шаг 2/4: Проверка GitHub авторизации"
if gh auth status >/dev/null 2>&1; then
  echo "[OK] gh auth активна"
else
  echo "[ПРОБЛЕМА] gh не авторизован. Выполни: gh auth login"
  exit 1
fi

echo "Шаг 3/4: Проверка обязательных переменных из .env.integrations"
set -a
source ./.env.integrations
set +a

missing=0
for v in SENTRY_AUTH_TOKEN SENTRY_ORG SENTRY_PROJECT OPENAI_API_KEY NOTION_TOKEN; do
  if [[ -n "${!v:-}" ]]; then
    echo "[OK] $v задан"
  else
    echo "[ПРОБЛЕМА] $v не задан"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "[ПРОБЛЕМА] Заполни .env.integrations и повтори запуск"
  exit 1
fi

echo "Шаг 4/4: Финальные проверки"
make preflight
make verify

echo "Готово: интеграции доведены до рабочего состояния"
