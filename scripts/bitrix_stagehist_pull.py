#!/usr/bin/env python3
"""Read-only выгрузка истории стадий воронки [10] + телефония-агрегат."""
import json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

STATE_PATH = Path(os.environ.get("BITRIX_APP_STATE_DIR",
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state")) / "install.latest.json"
OUT = Path("/tmp/funnel_analysis"); OUT.mkdir(exist_ok=True)

def auth():
    s = json.loads(STATE_PATH.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]

def call(method, params=None):
    endpoint, token = auth()
    flat = [("auth", token)]
    for k, v in (params or {}).items():
        flat.append((k, str(v)))
    data = urllib.parse.urlencode(flat).encode()
    req = urllib.request.Request(f"{endpoint}/{method}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())

# stagehistory: result.items, пагинация через start (50/стр), используем filter[>ID]
out = []
last_id = 0
for _ in range(5000):
    r = call("crm.stagehistory.list", {
        "entityTypeId": 2,
        "filter[CATEGORY_ID]": 10,
        "filter[>ID]": last_id,
        "order[ID]": "ASC",
        "start": -1,
        "select[0]": "ID", "select[1]": "OWNER_ID", "select[2]": "CREATED_TIME",
        "select[3]": "STAGE_SEMANTIC_ID", "select[4]": "STAGE_ID",
    })
    res = r.get("result") or {}
    items = res.get("items") if isinstance(res, dict) else res
    if not items:
        break
    out.extend(items)
    last_id = int(items[-1]["ID"])
    if len(items) < 50:
        break

(OUT / "stagehistory_cat10.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(f"stagehistory_cat10: {len(out)} rows")
if out:
    print("sample:", json.dumps(out[0], ensure_ascii=False))
