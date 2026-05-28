#!/usr/bin/env python3
"""
Read-only разведка прав ролей CRM и userfields компании.
Цель: понять, что можно настроить через API:
  1) Право "Игнорирование контроля дубликатов" в роли менеджера
  2) Сделать ИНН обязательным при создании компании
"""
from __future__ import annotations
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")


def auth():
    s = json.loads(STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def call(method, params=None):
    endpoint, token = auth()
    flat = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for it in v: flat.append((k, str(it)))
        else: flat.append((k, str(v)))
    req = urllib.request.Request(
        f"{endpoint}/{method}",
        data=urllib.parse.urlencode(flat).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def hr(t): print(f"\n{'='*72}\n{t}\n{'='*72}")


# 1. Список методов разрешений
hr("МЕТОДЫ Bitrix REST: что доступно для прав")
methods_to_try = [
    "crm.permissions.role.list",
    "crm.permissions.role.fields",
    "crm.permissions.role.relation.list",
    "user.access",
    "crm.permissions.user.fields",
    "crm.duplicate.findbycomm",
]
for m in methods_to_try:
    r = call(m, {})
    if "error" in r:
        print(f"  ✗ {m:50} {r.get('error')} — {r.get('error_description', '')[:60]}")
    else:
        res = r.get("result")
        if isinstance(res, (list, dict)):
            cnt = len(res)
        else:
            cnt = f"value={res}"
        print(f"  ✓ {m:50} OK ({cnt})")

# 2. Если crm.permissions.role.list работает — посмотреть роли
hr("РОЛИ CRM")
r = call("crm.permissions.role.list")
if r.get("result"):
    roles = r["result"]
    for role in roles:
        print(f"  id={role.get('ID')}  name={role.get('NAME')!r}")
else:
    print(f"  не доступно: {r.get('error_description', r.get('error', '???'))}")

# 3. Поля роли (чтобы найти ключ "ignore duplicate")
hr("ПОЛЯ РОЛИ (структура разрешений)")
r = call("crm.permissions.role.fields")
if r.get("result"):
    fields = r["result"]
    print(f"  записей: {len(fields) if isinstance(fields, (list, dict)) else '?'}")
    print(f"  raw (первые 2000 символов):")
    print(json.dumps(fields, ensure_ascii=False, indent=2)[:2000])
else:
    print(f"  не доступно: {r.get('error_description', '???')}")

# 4. UserFields компании — ищем ИНН и его обязательность
hr("USERFIELDS КОМПАНИИ (нестандартные поля)")
r = call("crm.company.userfield.list", {"order[SORT]": "ASC"})
if r.get("result"):
    for f in r["result"]:
        title = (f.get("EDIT_FORM_LABEL") or {}).get("ru") or f.get("FIELD_NAME")
        is_required = f.get("MANDATORY") == "Y"
        print(f"  {f.get('FIELD_NAME'):30} req={is_required}  title={title}")
else:
    print(f"  не доступно: {r.get('error_description', '???')}")

# 5. Системные поля компании — особенно ИНН
hr("СТАНДАРТНЫЕ ПОЛЯ КОМПАНИИ")
r = call("crm.company.fields")
if r.get("result"):
    for fname, finfo in r["result"].items():
        if "INN" in fname.upper() or "ИНН" in str(finfo).upper() or fname in ("TITLE", "COMPANY_TYPE"):
            print(f"  {fname:30} required={finfo.get('isRequired')}  type={finfo.get('type')}  title={finfo.get('title')}")
    print(f"  (всего полей: {len(r['result'])})")

# 6. Реквизит — там живёт ИНН
hr("ПОЛЯ РЕКВИЗИТА")
r = call("crm.requisite.fields")
if r.get("result"):
    for fname, finfo in r["result"].items():
        if "INN" in fname.upper() or "KPP" in fname.upper():
            print(f"  {fname:25} required={finfo.get('isRequired')}  type={finfo.get('type')}  title={finfo.get('title')}")

# 7. События — что можно подписать на onCrmCompanyAdd
hr("EVENT-ХЕНДЛЕРЫ")
r = call("event.get")
if r.get("result"):
    for ev in r["result"]:
        if "COMPANY" in str(ev.get("EVENT", "")).upper():
            print(f"  event={ev.get('EVENT')}  handler={(ev.get('HANDLER') or '')[:60]}  auth_type={ev.get('AUTH_TYPE')}")
    print(f"  (всего обработчиков: {len(r['result'])})")
else:
    print(f"  нет: {r.get('error_description', '???')}")
