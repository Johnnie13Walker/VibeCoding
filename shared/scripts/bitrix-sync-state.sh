#!/usr/bin/env bash

set -euo pipefail

LOCK_FILE="${BITRIX_SYNC_LOCK_FILE:-/tmp/bitrix-sync.lock}"
ENV_FILE="${BITRIX_ENV_FILE:-/opt/openclaw/.env}"
STATE_FILE="${BITRIX_STATE_PATH:-/opt/openclaw/state/bitrix_app/install.latest.json}"
TOKEN_URL="${BITRIX_OAUTH_TOKEN_URL:-https://oauth.bitrix24.tech/oauth/token/}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Bitrix sync failed: env file not found: $ENV_FILE" >&2
  exit 1
fi

(
  flock -x 200

  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a

  export BITRIX_STATE_PATH="${BITRIX_STATE_PATH:-$STATE_FILE}"
  export BITRIX_OAUTH_TOKEN_URL="${BITRIX_OAUTH_TOKEN_URL:-$TOKEN_URL}"

  python3 - <<'PY'
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def pick(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
        os.chmod(path, 0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


state_path = Path(os.environ.get("BITRIX_STATE_PATH", "/opt/openclaw/state/bitrix_app/install.latest.json"))
client_id = os.environ.get("BITRIX_CLIENT_ID", "").strip()
client_secret = os.environ.get("BITRIX_CLIENT_SECRET", "").strip()
token_url = os.environ.get("BITRIX_OAUTH_TOKEN_URL", "https://oauth.bitrix24.tech/oauth/token/").strip()

if not client_id:
    raise SystemExit("Bitrix sync failed: BITRIX_CLIENT_ID is empty")
if not client_secret:
    raise SystemExit("Bitrix sync failed: BITRIX_CLIENT_SECRET is empty")
if not state_path.exists():
    raise SystemExit(f"Bitrix sync failed: state file not found: {state_path}")

data = json.loads(state_path.read_text(encoding="utf-8"))
payload = data.get("payload")
if not isinstance(payload, dict):
    raise SystemExit("Bitrix sync failed: state payload missing")

refresh_token = pick(payload, "auth[refresh_token]", "REFRESH_ID", "refresh_token")
if not refresh_token:
    raise SystemExit("Bitrix sync failed: refresh_token missing")

request_body = urllib.parse.urlencode(
    {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
).encode("utf-8")

request = urllib.request.Request(
    token_url,
    method="POST",
    data=request_body,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
    refreshed = json.loads(response.read().decode("utf-8"))

access_token = refreshed.get("access_token")
new_refresh_token = refreshed.get("refresh_token") or refresh_token
expires_in = int(refreshed.get("expires_in") or 3600)
if not access_token:
    raise SystemExit("Bitrix sync failed: access_token missing in refresh response")

now = int(time.time())
expires_at = now + expires_in
client_endpoint = refreshed.get("client_endpoint") or pick(payload, "auth[client_endpoint]", "client_endpoint")
domain = refreshed.get("domain") or pick(payload, "auth[domain]", "domain")

payload["auth[access_token]"] = access_token
payload["AUTH_ID"] = access_token
payload["auth[refresh_token]"] = new_refresh_token
payload["REFRESH_ID"] = new_refresh_token
payload["auth[expires]"] = expires_at
payload["auth[expires_in]"] = expires_in
payload["expires_in"] = expires_in
if client_endpoint:
    payload["auth[client_endpoint]"] = client_endpoint
    payload["client_endpoint"] = client_endpoint
if domain:
    payload["auth[domain]"] = domain
    payload["domain"] = domain

data["auth_refreshed_at"] = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
write_json_atomic(state_path, data)

endpoint = str(client_endpoint or "").rstrip("/")
if not endpoint:
    raise SystemExit("Bitrix sync failed: client_endpoint missing after refresh")

profile_request = urllib.request.Request(
    endpoint + "/profile.json",
    method="POST",
    data=urllib.parse.urlencode({"auth": access_token}).encode("utf-8"),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
with urllib.request.urlopen(profile_request, timeout=30) as response:  # noqa: S310
    profile_body = json.loads(response.read().decode("utf-8"))

profile = profile_body.get("result") or {}
if not profile:
    raise SystemExit("Bitrix sync failed: profile probe returned empty result")

print(
    "Bitrix OK:"
    f" ID={profile.get('ID')}"
    f" NAME={profile.get('NAME')}"
    f" ADMIN={profile.get('ADMIN')}"
)
PY
) 200>"$LOCK_FILE"
