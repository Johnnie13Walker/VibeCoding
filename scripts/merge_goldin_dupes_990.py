#!/usr/bin/env python3
"""Свести дубли контакта Гольдина в сделке #990 к одному (#75112).

Read-only прогон (22.06.2026) показал: 11 дублей — пустые сироты
(0 сделок, 0 активностей, COMPANY_ID=None). Удаление идёт в корзину Bitrix
(обратимо ~30 дней). Мобильного телефона у Гольдина нет — везде городской
8(499)235-53-50, поэтому приоритет «мобильный» неприменим.

Запуск: python3 scripts/merge_goldin_dupes_990.py
"""
import json, urllib.parse, urllib.request, urllib.error

STATE = "shared/config/bitrix24-state/install.latest.json"
s = json.loads(open(STATE).read())["payload"]
endpoint = s["auth[client_endpoint]"].rstrip("/")
token = s["auth[access_token]"]

CANON = 75112
DUPES = [77716, 92382, 92386, 92388, 92464, 92466, 92468, 92514, 92516, 92518, 92716]


def call(method, params):
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


# Предохранитель: повторно убедиться, что дубль действительно пустой
for cid in DUPES:
    deals = call("crm.deal.list", [("filter[CONTACT_ID]", str(cid)), ("select[]", "ID")]).get("result", [])
    acts = call("crm.activity.list", [("filter[OWNER_TYPE_ID]", "3"), ("filter[OWNER_ID]", str(cid)), ("select[]", "ID")]).get("result", [])
    if deals or acts:
        print(f"СТОП: #{cid} не пустой (сделок={len(deals)}, активностей={len(acts)}) — пропуск")
        DUPES = [x for x in DUPES if x != cid]

# 1) Отвязать дубли от сделки 990
for cid in DUPES:
    r = call("crm.deal.contact.delete", [("id", "990"), ("fields[CONTACT_ID]", str(cid))])
    print(f"unbind #{cid} от 990 -> {r.get('result', r.get('error_description'))}")

# 2) Удалить пустые контакты-сироты (в корзину)
for cid in DUPES:
    r = call("crm.contact.delete", [("id", str(cid))])
    print(f"delete #{cid} -> {r.get('result', r.get('error_description'))}")

# 3) Контрольная сверка
print("\n=== КОНТАКТЫ СДЕЛКИ 990 ПОСЛЕ ЧИСТКИ ===")
items = call("crm.deal.contact.items.get", [("id", "990")]).get("result", [])
for it in items:
    c = call("crm.contact.get", [("id", str(it["CONTACT_ID"]))]).get("result", {})
    ph = ", ".join(p["VALUE"] for p in (c.get("PHONE") or []))
    primary = " (основной)" if it["IS_PRIMARY"] == "Y" else ""
    print(f"  #{it['CONTACT_ID']}{primary}: {c.get('NAME','')} {c.get('LAST_NAME','')} | {c.get('POST') or '—'} | {ph or '—'}")
