#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

printf "=== SMOKE HAPP IMPORT (%s) ===\n" "$(date '+%F %T %Z')"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "[OK] DRY-RUN: smoke import пропущен"
  exit 0
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

curl_opts="-fsS --max-time 10"
if [[ "${SUBSCRIPTION_INSECURE_TLS:-0}" == "1" ]]; then
  curl_opts="-k ${curl_opts}"
fi

if ! eval "curl ${curl_opts} \"$SUBSCRIPTION_URL\"" -o "$tmp_file"; then
  ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${SSH_USER}@${PRIMARY_HOST}" \
    "curl -fsS --max-time 10 http://127.0.0.1${SUBSCRIPTION_PATH:-/subscription/happ.txt}" >"$tmp_file"
fi

count="$(grep -Ec '^vless://' "$tmp_file" || true)"
min_nodes=1
if [[ -n "${RESERVE_HOST:-}" ]]; then
  min_nodes=2
fi
if [[ "$count" -lt "$min_nodes" ]]; then
  echo "[WARN] В подписке меньше ${min_nodes} нод: $count"
  exit 1
fi

grep -q "#${PRIMARY_NODE_NAME:-happ-main}" "$tmp_file"
if [[ -n "${RESERVE_HOST:-}" ]]; then
  grep -q "#${RESERVE_NODE_NAME:-happ-backup}" "$tmp_file"
fi

echo "[OK] Подписка импортопригодна для Happ"
