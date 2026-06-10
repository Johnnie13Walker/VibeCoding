#!/usr/bin/env python3
"""bitrix_audit.py — материалы сделки из Bitrix24 для смыслового блока КП.

По ID сделки собирает: ядро сделки (домен, компания, контакт, выручка, услуги),
бриф СП1056 с ПОДПИСЯМИ полей (читаемые ответы), транскрипт встречи СП1048,
переписку Wazzup. Это сырьё для потребностей / среднего чека / ЛПР / конкурентов.

Доступ — общий state: shared/config/bitrix24-state/install.latest.json
(перед запуском синкнуть: bash shared/scripts/bitrix-sync-state.sh).

Использование:
    python3 bitrix_audit.py <deal_id>
    python3 bitrix_audit.py 12866

Выход: bitrix.json (сделка + бриф-ответы + транскрипт + Wazzup) + краткий отчёт.
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

STATE = os.path.expanduser(
    "~/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
_s = json.loads(open(STATE, encoding="utf-8").read())["payload"]
EP = _s["auth[client_endpoint]"].rstrip("/")
TOK = _s["auth[access_token]"]


def call(method, params=None):
    flat = []

    def enc(prefix, v):
        if isinstance(v, dict):
            for k, val in v.items():
                enc(f"{prefix}[{k}]", val)
        elif isinstance(v, (list, tuple)):
            for i, val in enumerate(v):
                enc(f"{prefix}[{i}]", val)
        else:
            flat.append((prefix, v))
    for k, v in (params or {}).items():
        enc(k, v)
    data = urllib.parse.urlencode([("auth", TOK), *flat]).encode()
    req = urllib.request.Request(f"{EP}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def brief_fields_titles() -> dict:
    """ufCrm20_* → человеческая подпись поля брифа (СП1056)."""
    r = call("crm.item.fields", {"entityTypeId": 1056}).get("result", {})
    fields = r.get("fields", r)
    return {k: (v.get("title") or k) for k, v in fields.items()}


def main():
    if len(sys.argv) < 2:
        print("usage: bitrix_audit.py <deal_id>")
        sys.exit(1)
    deal_id = int(sys.argv[1])

    deal = call("crm.deal.get", {"id": deal_id}).get("result", {})
    if not deal:
        sys.exit(f"⚠ Сделка {deal_id} не найдена (или нет доступа — синкни state).")

    out = {
        "deal_id": deal_id,
        "title": deal.get("TITLE"),
        "stage": deal.get("STAGE_ID"),
        "opportunity": deal.get("OPPORTUNITY"),
        "company_id": deal.get("COMPANY_ID"),
        "contact_id": deal.get("CONTACT_ID"),
        "site": deal.get("UF_CRM_69E8AB2E0715A"),
        "company_revenue": deal.get("UF_CRM_1774971054"),
        "services_note": deal.get("UF_CRM_1775402408"),
        "brief": {},
        "transcript": None,
        "wazzup": [],
    }

    # бриф СП1056 по сделке — ответы с подписями
    briefs = call("crm.item.list", {"entityTypeId": 1056,
                                     "filter": {"parentId2": deal_id}}).get("result", {}).get("items", [])
    if briefs:
        titles = brief_fields_titles()
        b = briefs[0]
        for k, v in b.items():
            if k.startswith("ufCrm20_") and isinstance(v, str) and v.strip():
                out["brief"][titles.get(k, k)] = v

    # встреча СП1048 → транскрипт (текст)
    meets = call("crm.item.list", {"entityTypeId": 1048,
                                    "filter": {"parentId2": deal_id}}).get("result", {}).get("items", [])
    if meets:
        full = call("crm.item.get", {"entityTypeId": 1048, "id": meets[0]["id"]}).get("result", {}).get("item", {})
        tr = full.get("ufCrm16Transcript")
        if isinstance(tr, dict) and tr.get("urlMachine"):
            try:
                with urllib.request.urlopen(tr["urlMachine"], timeout=60) as r:
                    out["transcript"] = r.read().decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                out["transcript"] = "(не удалось скачать транскрипт)"

    # Wazzup / таймлайн
    cm = call("crm.timeline.comment.list",
              {"filter": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal"},
               "select": ["CREATED", "AUTHOR_ID", "COMMENT"]}).get("result", [])
    out["wazzup"] = [{"at": c.get("CREATED"), "author": c.get("AUTHOR_ID"),
                      "text": (c.get("COMMENT") or "")[:600]} for c in cm]

    json.dump(out, open("bitrix.json", "w"), ensure_ascii=False, indent=2)

    print(f"# Сделка {deal_id} — {out['title']}  ({out['stage']})")
    print(f"  сайт={out['site']}  выручка_компании={out['company_revenue']}  услуги={out['services_note']}")
    print(f"  бриф-ответов: {len(out['brief'])}  транскрипт: {'есть' if out['transcript'] else 'нет'}  "
          f"Wazzup-сообщений: {len(out['wazzup'])}")
    if out["brief"]:
        print("  ключевые ответы брифа:")
        for k, v in list(out["brief"].items())[:12]:
            print(f"    {k}: {v[:70]}")
    print("→ bitrix.json (полный материал для смыслового блока КП)")


if __name__ == "__main__":
    main()
