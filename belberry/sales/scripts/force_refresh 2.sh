#!/usr/bin/env bash
# Принудительный refresh Bitrix OAuth access token, без рассылки.
# Запуск на проде:
#   bash force_refresh.sh
set -eu

cd /opt/cloudbot-runtime/current
set -a
. /opt/openclaw/.env
. /etc/openclaw/sales_agent.env
set +a

python3 - <<'PY'
import os, json
from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth, BitrixAPIError

# Конструктор требует kwargs; from_env(os.environ) сам подтянет BITRIX_APP_STATE_DIR,
# BITRIX_CLIENT_ID, BITRIX_CLIENT_SECRET и т.д.
auth = BitrixAppAuth.from_env(os.environ)
state_before = auth.load_state()
print("BEFORE")
print("  saved_at         =", state_before.record.get("saved_at"))
print("  auth_refreshed_at=", state_before.record.get("auth_refreshed_at"))
print("  domain           =", state_before.domain)
print("  has_access       =", bool(state_before.access_token))
print("  has_refresh      =", bool(state_before.refresh_token))
print()
try:
    state = auth.refresh_access_token()
except BitrixAPIError as exc:
    print("REFRESH FAILED")
    print("  code     =", exc.code)
    print("  category =", exc.category)
    print("  http     =", exc.http_status)
    print("  message  =", exc.message)
    raise SystemExit(1)
print("AFTER refresh_access_token()")
print("  saved_at         =", state.record.get("saved_at"))
print("  auth_refreshed_at=", state.record.get("auth_refreshed_at"))
print("  domain           =", state.domain)
print("  has_access       =", bool(state.access_token))
print("  has_refresh      =", bool(state.refresh_token))

# Smoke: дернуть user.current под обновлённым state, без рассылки.
payload = auth.call_payload("user.current", default={})
result = payload.get("result") or {}
print("user.current ->",
      "id=", result.get("ID"),
      "name=", result.get("NAME"),
      "last=", result.get("LAST_NAME"))
PY

echo
echo "Force refresh OK"
