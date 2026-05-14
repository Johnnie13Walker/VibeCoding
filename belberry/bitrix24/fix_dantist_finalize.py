"""
fix_dantist_finalize.py — детерминированно прописывает правильные реквизиты в 4
карточки ДАНТИСТЪ. BP 5614 не отрабатывает (видимо guard на уровне компании
после прежнего прогона по неверному ИНН) — берём данные из rusprofile напрямую.

Шаги:
  #4742 → update req#17400 (создан скриптом fix_dantist_inns) с полным набором.
  #8360, #8762, #9618 → update существующего «неверного» реквизита, переписав
                        ВСЕ поля на правильные. Старый INN 5250071606 заменится
                        in-place, не нужно add/delete.

Также:
  - Обновить UF_CRM_1737098445351 (юр.адрес на самой компании) на правильный.
  - Для #9618 поправить UF_CRM_1584876724 (Город) с «Химки» на «Калуга».
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BITRIX_STATE = Path(
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json"
)

UF_ADDR = "UF_CRM_1737098445351"
UF_CITY = "UF_CRM_1584876724"

FIXES = [
    {
        "cid": "4742",
        "req_id": "17400",
        "city": None,  # уже "Москва"
        "rq": {
            "RQ_INN": "7719429754",
            "RQ_KPP": "770101001",
            "RQ_OGRN": "5157746032990",
            "RQ_COMPANY_NAME": "ООО \"Стоматологическая Клиника \"Дантистъ\"",
            "RQ_COMPANY_FULL_NAME": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТЪ\"",
            "RQ_ADDR": "101000, город Москва, Архангельский пер., д. 7 стр. 1, пом. I комн. с 1 по 13",
            "NAME": "Реквизиты ЮЛ",
        },
        "addr_uf": "101000, город Москва, Архангельский пер., д. 7 стр. 1, пом. I комн. с 1 по 13",
    },
    {
        "cid": "8360",
        "req_id": "6514",
        "city": None,  # уже "Серпухов"
        "rq": {
            "RQ_INN": "5043031718",
            "RQ_KPP": "504301001",
            "RQ_OGRN": "1075043002968",
            "RQ_COMPANY_NAME": "ООО Стоматологическая Клиника \"Дантист\"",
            "RQ_COMPANY_FULL_NAME": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТ\"",
            "RQ_ADDR": "142200, Московская область, город Серпухов, пр-д Мишина, д. 11, 111",
            "NAME": "Реквизиты ЮЛ",
        },
        "addr_uf": "142200, Московская область, город Серпухов, пр-д Мишина, д. 11, 111",
    },
    {
        "cid": "8762",
        "req_id": "6424",
        "city": None,  # уже "Санкт-Петербург"
        "rq": {
            "RQ_INN": "7816328303",
            "RQ_KPP": "781601001",
            "RQ_OGRN": "1167847217812",
            "RQ_COMPANY_NAME": "ООО \"Дантистъ\"",
            "RQ_COMPANY_FULL_NAME": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"ДАНТИСТЪ\"",
            "RQ_ADDR": "192212, Санкт-Петербург, Будапештская ул., д. 29 к. 1 литер а, пом. 5-н оф. 1",
            "NAME": "Реквизиты ЮЛ",
        },
        "addr_uf": "192212, Санкт-Петербург, Будапештская ул., д. 29 к. 1 литер а, пом. 5-н оф. 1",
    },
    {
        "cid": "9618",
        "req_id": "6156",
        "city": "Калуга",  # текущее значение "Химки" — неверно
        "rq": {
            "RQ_INN": "4027063559",
            "RQ_KPP": "402701001",
            "RQ_OGRN": "1044004401968",
            "RQ_COMPANY_NAME": "ООО \"Дантист\"",
            "RQ_COMPANY_FULL_NAME": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТ\"",
            "RQ_ADDR": "248001, Калужская область, город Калуга, ул. Кирова, д. 47",
            "NAME": "Реквизиты ЮЛ",
        },
        "addr_uf": "248001, Калужская область, город Калуга, ул. Кирова, д. 47",
    },
]


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def call(method, params, max_tries=4):
    s = json.loads(BITRIX_STATE.read_text())["payload"]
    url = f"{s['auth[client_endpoint]'].rstrip('/')}/{method}"
    data = urllib.parse.urlencode([("auth", s["auth[access_token]"]), *params]).encode()
    for attempt in range(max_tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                time.sleep(min(20, 2 ** attempt))
                continue
            raise RuntimeError(f"{method} HTTP {e.code}: {body[:300]}") from e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cid", action="append")
    args = ap.parse_args()
    fixes = [f for f in FIXES if (not args.cid or f["cid"] in args.cid)]
    log(f"finalize: {len(fixes)} cards (dry_run={args.dry_run})")

    for f in fixes:
        cid = f["cid"]
        req_id = f["req_id"]
        log(f"=== #{cid} → req#{req_id} INN={f['rq']['RQ_INN']} ===")

        # ВАЖНО: перед update проверим что req существует и принадлежит этой компании
        cur = call("crm.requisite.get", [("ID", req_id)]).get("result") or {}
        if str(cur.get("ENTITY_ID")) != cid:
            log(f"  !!! req#{req_id} принадлежит ENTITY_ID={cur.get('ENTITY_ID')}, ожидался {cid} — пропускаю")
            continue
        log(f"  до update: INN={cur.get('RQ_INN')} KPP={cur.get('RQ_KPP')} OGRN={cur.get('RQ_OGRN')}")

        if args.dry_run:
            for k, v in f["rq"].items():
                log(f"  [DRY] set {k} = {v!r}")
            log(f"  [DRY] company UF_ADDR = {f['addr_uf']!r}")
            if f["city"]:
                log(f"  [DRY] company UF_CITY = {f['city']!r}")
            continue

        # 1. requisite.update
        params = [("ID", req_id)]
        for k, v in f["rq"].items():
            params.append((f"fields[{k}]", v))
        try:
            call("crm.requisite.update", params)
            log(f"  ✓ requisite updated")
        except Exception as e:
            log(f"  !!! requisite.update error: {e}")
            continue

        # 2. company UF fields
        comp_params = [("ID", cid)]
        if f["addr_uf"]:
            comp_params.append((f"fields[{UF_ADDR}]", f["addr_uf"]))
        if f["city"]:
            comp_params.append((f"fields[{UF_CITY}]", f["city"]))
        try:
            call("crm.company.update", comp_params)
            log(f"  ✓ company UF updated")
        except Exception as e:
            log(f"  !!! company.update error: {e}")

        # 3. verify
        v = call("crm.requisite.get", [("ID", req_id)]).get("result") or {}
        log(f"  verify: INN={v.get('RQ_INN')} KPP={v.get('RQ_KPP')} OGRN={v.get('RQ_OGRN')} NAME={v.get('RQ_COMPANY_NAME')!r}")


if __name__ == "__main__":
    main()
