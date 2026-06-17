#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage:
  bitrix_oauth_helper.sh auth-url
  bitrix_oauth_helper.sh exchange-code <code>
  bitrix_oauth_helper.sh refresh

Required env:
  BITRIX_PORTAL_URL (e.g. https://yourcompany.bitrix24.ru)
  BITRIX_CLIENT_ID
  BITRIX_CLIENT_SECRET
  BITRIX_REDIRECT_URI

Optional env:
  BITRIX_OAUTH_TOKEN_FILE (default: /tmp/clawbot-cache/bitrix-oauth.json)
  BITRIX_SCOPE (default: calendar,user)
USAGE
}

require_env() {
  local k
  for k in "$@"; do
    if [ -z "${!k:-}" ]; then
      echo "Missing env: $k" >&2
      exit 1
    fi
  done
}

portal_origin() {
  local p="${BITRIX_PORTAL_URL:-}"
  if [ -z "$p" ]; then
    echo ""; return
  fi
  if [[ "$p" =~ ^https?:// ]]; then
    echo "${p%/}"
  else
    echo "https://${p%/}"
  fi
}

token_file() {
  echo "${BITRIX_OAUTH_TOKEN_FILE:-/tmp/clawbot-cache/bitrix-oauth.json}"
}

auth_url() {
  require_env BITRIX_PORTAL_URL BITRIX_CLIENT_ID BITRIX_REDIRECT_URI
  local origin
  origin="$(portal_origin)"
  local scope="${BITRIX_SCOPE:-calendar,user}"
  printf '%s/oauth/authorize/?client_id=%s&response_type=code&redirect_uri=%s&scope=%s\n' \
    "$origin" "$BITRIX_CLIENT_ID" "$BITRIX_REDIRECT_URI" "$scope"
}

write_token_json() {
  local json="$1"
  local f
  f="$(token_file)"
  mkdir -p "$(dirname "$f")"
  printf '%s' "$json" > "$f"
  chmod 600 "$f" || true
  echo "saved: $f"
}

normalize_token_json() {
  python3 -c 'import json,sys,time; d=json.load(sys.stdin); err=d.get("error_description") or d.get("error"); 
if err: raise SystemExit("oauth error: " + str(err))
acc=d.get("access_token",""); ref=d.get("refresh_token",""); exp=int(d.get("expires_in",0) or 0)
print(json.dumps({"access_token":acc,"refresh_token":ref,"expires_at":int(time.time()*1000)+exp*1000 if exp>0 else 0}))'
}

exchange_code() {
  require_env BITRIX_PORTAL_URL BITRIX_CLIENT_ID BITRIX_CLIENT_SECRET BITRIX_REDIRECT_URI
  local code="${1:-}"
  if [ -z "$code" ]; then
    echo "Missing arg: code" >&2
    exit 1
  fi
  local origin
  origin="$(portal_origin)"

  local res
  res="$(curl -sS -G "${origin}/oauth/token/" \
    --data-urlencode "grant_type=authorization_code" \
    --data-urlencode "client_id=${BITRIX_CLIENT_ID}" \
    --data-urlencode "client_secret=${BITRIX_CLIENT_SECRET}" \
    --data-urlencode "code=${code}" \
    --data-urlencode "redirect_uri=${BITRIX_REDIRECT_URI}")"

  local out
  out="$(printf '%s' "$res" | normalize_token_json)"
  write_token_json "$out"
  printf '%s\n' "$out"
}

refresh_token() {
  require_env BITRIX_PORTAL_URL BITRIX_CLIENT_ID BITRIX_CLIENT_SECRET
  local origin
  origin="$(portal_origin)"
  local f
  f="$(token_file)"
  if [ ! -f "$f" ]; then
    echo "Token file not found: $f" >&2
    exit 1
  fi

  local refresh
  refresh="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("refresh_token", ""))' "$f")"
  if [ -z "$refresh" ]; then
    echo "refresh_token is empty in: $f" >&2
    exit 1
  fi

  local res
  res="$(curl -sS -G "${origin}/oauth/token/" \
    --data-urlencode "grant_type=refresh_token" \
    --data-urlencode "client_id=${BITRIX_CLIENT_ID}" \
    --data-urlencode "client_secret=${BITRIX_CLIENT_SECRET}" \
    --data-urlencode "refresh_token=${refresh}")"

  local out
  out="$(printf '%s' "$res" | normalize_token_json)"
  write_token_json "$out"
  printf '%s\n' "$out"
}

cmd="${1:-}"
case "$cmd" in
  auth-url)
    auth_url
    ;;
  exchange-code)
    shift
    exchange_code "${1:-}"
    ;;
  refresh)
    refresh_token
    ;;
  *)
    usage
    exit 1
    ;;
esac
