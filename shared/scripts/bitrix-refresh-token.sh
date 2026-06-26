#!/usr/bin/env bash
# Refresh Bitrix24 OAuth токена через oauth.bitrix24.tech.
# Обновляет state локально + на VPS. Запускать когда sync не помогает (state на VPS тоже стар).
set -euo pipefail

ROOT="/Users/pro2kuror/Desktop/VibeCoding"
STATE_LOCAL="$ROOT/shared/config/bitrix24-state/install.latest.json"
STATE_REMOTE="cloudbot-hz:/opt/openclaw/state/bitrix_app/install.latest.json"

# Загружаем credentials
set -a
. "$ROOT/.env.integrations"
set +a

if [ -z "${BITRIX_CLIENT_ID:-}" ] || [ -z "${BITRIX_CLIENT_SECRET:-}" ]; then
    echo "BITRIX_CLIENT_ID / BITRIX_CLIENT_SECRET не заданы в .env.integrations" >&2
    exit 1
fi

python3 - <<PY
import json, urllib.parse, urllib.request, time, shutil, os
from pathlib import Path

STATE = Path("$STATE_LOCAL")
ts = time.strftime('%Y%m%d_%H%M%S')
backup = STATE.with_suffix(f'.json.before_refresh_{ts}')
shutil.copy2(STATE, backup)

d = json.loads(STATE.read_text())
refresh = d['payload']['auth[refresh_token]']

req = urllib.request.Request(
    "https://oauth.bitrix24.tech/oauth/token?" + urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": os.environ["BITRIX_CLIENT_ID"],
        "client_secret": os.environ["BITRIX_CLIENT_SECRET"],
        "refresh_token": refresh,
    }),
)
with urllib.request.urlopen(req, timeout=30) as r:
    fresh = json.loads(r.read())

if 'error' in fresh:
    raise SystemExit(f"OAuth refresh failed: {fresh}")

new_payload = dict(d['payload'])
for k, v in fresh.items():
    new_payload[f"auth[{k}]"] = v
for k in ('access_token','refresh_token','expires','expires_in','scope','domain',
         'member_id','status','client_endpoint','server_endpoint','user_id'):
    if k in fresh:
        new_payload[k] = fresh[k]
new_payload['AUTH_ID'] = fresh['access_token']
new_payload['REFRESH_ID'] = fresh['refresh_token']

d['payload'] = new_payload
d['saved_at'] = time.strftime('%Y-%m-%dT%H:%M:%S+03:00', time.localtime())
d['auth_refreshed_at'] = d['saved_at']
STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2))
os.chmod(STATE, 0o600)

print(f"Refreshed OK (backup: {backup.name})")
print(f"  expires_in={fresh.get('expires_in')} scope={fresh.get('scope')}")
PY

# Заливаем на VPS чтобы cloudbot имел свежие данные
scp -q "$STATE_LOCAL" "$STATE_REMOTE"
ssh cloudbot-hz "chmod 600 /opt/openclaw/state/bitrix_app/install.latest.json"

# Проверка профиля
python3 - <<PY
import json, urllib.parse, urllib.request
s = json.loads(open("$STATE_LOCAL").read())['payload']
endpoint = s['auth[client_endpoint]']
token = s['auth[access_token]']
req = urllib.request.Request(endpoint + "profile.json", data=urllib.parse.urlencode({"auth": token}).encode())
with urllib.request.urlopen(req, timeout=30) as r:
    body = json.loads(r.read())
res = body.get('result', {})
print(f"Bitrix OK: ID={res.get('ID')} NAME={res.get('NAME')} LAST_NAME={res.get('LAST_NAME','')} ADMIN={res.get('ADMIN')}")
PY
