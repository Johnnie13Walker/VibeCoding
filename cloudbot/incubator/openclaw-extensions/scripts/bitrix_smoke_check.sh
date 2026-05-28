#!/usr/bin/env bash
set -euo pipefail

if [ -z "${BITRIX_PORTAL_URL:-}" ]; then
  echo "Missing env: BITRIX_PORTAL_URL" >&2
  exit 1
fi

TOKEN_FILE="${BITRIX_OAUTH_TOKEN_FILE:-/tmp/clawbot-cache/bitrix-oauth.json}"
if [ ! -f "$TOKEN_FILE" ]; then
  echo "Token file not found: $TOKEN_FILE" >&2
  exit 1
fi

ACCESS_TOKEN="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("access_token", ""))' "$TOKEN_FILE")"
if [ -z "$ACCESS_TOKEN" ]; then
  echo "access_token is empty in: $TOKEN_FILE" >&2
  exit 1
fi

if [[ "$BITRIX_PORTAL_URL" =~ ^https?:// ]]; then
  ORIGIN="${BITRIX_PORTAL_URL%/}"
else
  ORIGIN="https://${BITRIX_PORTAL_URL%/}"
fi

call() {
  local method="$1"
  curl -sS -G "${ORIGIN}/rest/${method}.json" --data-urlencode "auth=${ACCESS_TOKEN}"
}

echo "== user.current =="
call "user.current" | python3 -m json.tool

echo "== calendar.section.get =="
call "calendar.section.get" | python3 -m json.tool

echo "OK"
