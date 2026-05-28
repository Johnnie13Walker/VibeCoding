#!/usr/bin/env bash
# Диагностика Bitrix OAuth state на проде.
# Запуск: bash diagnose_oauth.sh
# Не печатает секреты — только маскированные хвосты.
set -u

STATE_DIR="${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}"
LOG_FILE="${SALES_LOG_FILE:-/home/ops/cloudbot-sales-agent/reports/sales_agent.log}"
REPORT_DIR="${REPORT_DIR:-/home/ops/cloudbot-sales-agent/reports}"

echo "=== ENV ==="
echo "TZ=$(date '+%Z')"
echo "Now: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "BITRIX_APP_STATE_DIR=$STATE_DIR"
echo "SALES_LOG_FILE=$LOG_FILE"
echo

echo "=== Bitrix state files (latest 10) ==="
if [ -d "$STATE_DIR" ]; then
  ls -lt "$STATE_DIR" 2>/dev/null | head -12
else
  echo "STATE_DIR not found"
fi
echo

echo "=== install.latest.json / handler.latest.json summary ==="
python3 - <<'PY'
import json, os, sys
from pathlib import Path

state_dir = Path(os.environ.get("BITRIX_APP_STATE_DIR", "/opt/openclaw/state/bitrix_app"))
candidates = sorted(state_dir.glob("install.*.json")) + sorted(state_dir.glob("handler.*.json"))
named = [
    state_dir / "install.latest.json",
    state_dir / "handler.latest.json",
]

def mask(value):
    s = str(value or "")
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]} (len={len(s)})"

def dump(path: Path):
    if not path.exists():
        print(f"  [missing] {path.name}")
        return
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f"  [bad json] {path.name}: {exc}")
        return
    payload = data.get("payload") or {}
    auth = {k: v for k, v in payload.items() if k.startswith("auth[")}
    print(f"  [{path.name}]")
    print(f"    saved_at           = {data.get('saved_at')}")
    print(f"    auth_refreshed_at  = {data.get('auth_refreshed_at')}")
    print(f"    domain             = {payload.get('auth[domain]')}")
    print(f"    member_id          = {payload.get('auth[member_id]')}")
    print(f"    status             = {payload.get('auth[status]')}")
    print(f"    client_endpoint    = {payload.get('auth[client_endpoint]')}")
    print(f"    server_endpoint    = {payload.get('auth[server_endpoint]')}")
    print(f"    access_token       = {mask(payload.get('auth[access_token]'))}")
    print(f"    refresh_token      = {mask(payload.get('auth[refresh_token]'))}")
    print(f"    fields present     = {sorted(auth.keys())}")

for path in named:
    dump(path)

# Find the file the loader would actually pick (latest saved_at).
def saved_at(path: Path):
    try:
        return json.loads(path.read_text()).get("saved_at") or ""
    except Exception:
        return ""

for prefix in ("install", "handler"):
    files = sorted(state_dir.glob(f"{prefix}.*.json"), key=saved_at, reverse=True)[:3]
    print(f"\nTop 3 {prefix}.*.json by saved_at:")
    for f in files:
        print(f"  {saved_at(f)}  {f.name}")
PY
echo

echo "=== OAuth refresh endpoints reachability ==="
for url in https://oauth.bitrix.info/oauth/token/ https://oauth.bitrix24.tech/oauth/token/ ; do
  printf '  %-50s -> ' "$url"
  curl -sS -o /dev/null -w 'HTTP %{http_code} (%{time_total}s)\n' --max-time 8 -X POST "$url" -d 'grant_type=refresh_token' || echo "FAIL"
done
echo

echo "=== Last 30 sales_agent.log events ==="
if [ -f "$LOG_FILE" ]; then
  tail -n 30 "$LOG_FILE"
else
  echo "$LOG_FILE not found"
fi
echo

echo "=== Today's sales_morning_report*.txt (head) ==="
TODAY=$(date '+%Y%m%d')
for f in "$REPORT_DIR"/sales_morning_report_${TODAY}_*.txt; do
  [ -f "$f" ] || continue
  echo "--- $f ---"
  head -20 "$f"
done

echo
echo "=== Done ==="
