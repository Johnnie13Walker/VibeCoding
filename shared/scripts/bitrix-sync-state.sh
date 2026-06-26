#!/usr/bin/env bash

set -euo pipefail

ROOT="/Users/pro2kuror/Desktop/VibeCoding"
REMOTE_STATE="cloudbot-hz:/opt/openclaw/state/bitrix_app/install.latest.json"
LOCAL_STATE_DIR="$ROOT/shared/config/bitrix24-state"
LOCAL_STATE_FILE="$LOCAL_STATE_DIR/install.latest.json"

mkdir -p "$LOCAL_STATE_DIR"

scp -q "$REMOTE_STATE" "$LOCAL_STATE_FILE"
chmod 600 "$LOCAL_STATE_FILE"

python3 - <<'PY'
from pathlib import Path
import json
import urllib.parse
import urllib.request

state = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
data = json.loads(state.read_text())
payload = data.get("payload", {})
endpoint = (payload.get("auth[client_endpoint]") or payload.get("client_endpoint") or "").rstrip("/")
token = payload.get("auth[access_token]") or payload.get("AUTH_ID") or ""

if not endpoint:
    raise SystemExit("Bitrix sync failed: client_endpoint missing")
if not token:
    raise SystemExit("Bitrix sync failed: access_token missing")

request = urllib.request.Request(
    endpoint + "/profile.json",
    data=urllib.parse.urlencode({"auth": token}).encode(),
)

with urllib.request.urlopen(request, timeout=30) as response:
    body = json.loads(response.read().decode())

result = body.get("result", {})
print(
    "Bitrix OK:"
    f" ID={result.get('ID')}"
    f" NAME={result.get('NAME')}"
    f" LAST_NAME={result.get('LAST_NAME')}"
    f" ADMIN={result.get('ADMIN')}"
)
PY
