#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$BASE_DIR/.env"
FALLBACK_ENV="/opt/projects/.autopilot.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
elif [[ -f "$FALLBACK_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$FALLBACK_ENV"
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
MESSAGE="${1:-}"

if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" || -z "$MESSAGE" ]]; then
  echo "Telegram notify skipped: missing token/chat/message"
  exit 0
fi

curl -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}" \
  -d "disable_web_page_preview=true" \
  >/dev/null

echo "Telegram notify sent"

