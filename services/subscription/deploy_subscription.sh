#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

: "${SUBSCRIPTION_OUTPUT_PATH:=$ROOT_DIR/services/subscription/happ_subscription.txt}"
: "${PRIMARY_ENDPOINT_HOST:=${PRIMARY_HOST:-$HAPP_DOMAIN}}"

cat >"$SUBSCRIPTION_OUTPUT_PATH" <<SUB
# Happ subscription generated at $(date '+%F %T %Z')
# Формат: URI per line
# Вставьте реальные UUID/ключи/публичные параметры перед production deploy.
vless://REPLACE_UUID@${PRIMARY_ENDPOINT_HOST}:${VPN_PORT:-443}?type=tcp&security=reality&sni=www.cloudflare.com&fp=chrome&pbk=REPLACE_PUBLIC_KEY&sid=0123456789abcdef#${PRIMARY_NODE_NAME:-happ-main}
SUB

if [[ -n "${RESERVE_HOST:-}" ]]; then
  cat >>"$SUBSCRIPTION_OUTPUT_PATH" <<SUB
vless://REPLACE_UUID@${RESERVE_HOST}:${VPN_PORT:-443}?type=tcp&security=reality&sni=www.cloudflare.com&fp=chrome&pbk=REPLACE_PUBLIC_KEY&sid=0123456789abcdef#${RESERVE_NODE_NAME:-happ-backup}
SUB
fi

echo "Сформирован subscription файл: $SUBSCRIPTION_OUTPUT_PATH"
