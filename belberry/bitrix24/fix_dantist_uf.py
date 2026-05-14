"""
fix_dantist_uf.py — добивает 4 карточки ДАНТИСТЪ, перезаписывая company-level UF
полями настоящих юр.лиц (взято из rusprofile 2026-05-14).

Bitrix хранит реквизиты в двух местах: crm.requisite (поправлено
fix_dantist_finalize.py) и зеркальные UF на самой company (видны в списках
и фильтрах UI). UI-кнопка «Заполнение по ИНН» не сработала, поэтому пишем
UF напрямую.

Поля:
  TITLE                            — краткое юр.название
  UF_CRM_1735331882180             — ИНН плоский (виден в UI колонке ИНН)
  UF_CRM_1737098414068             — полное юр.название (ОБЩЕСТВО С ...)
  UF_CRM_1737098422264             — краткое название (дубль TITLE)
  UF_CRM_1737098430305             — ОГРН
  UF_CRM_1737098445351             — юр.адрес (уже есть, оставляем)
  UF_CRM_1737098484851             — ФИО руководителя
  UF_CRM_1737098491861             — должность
  UF_CRM_1737098498983             — численность сотрудников
  UF_CRM_1737098549301             — годовой оборот (выручка)
  UF_CRM_1737098476975             — Бренд проекта = "Belberry" (медицина)
  UF_CRM_5DEF838D882A2             — Сайт клиента (только для #4742, остальные ОК)

После записи запускается bizproc.workflow.start 5614 — best-effort,
если у портала ещё что-то подхватится.
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

BITRIX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
BACKUP_DIR = Path(__file__).parent / "backups" / "dantist_inn_fix"

UF = {
    "INN": "UF_CRM_1735331882180",
    "OGRN": "UF_CRM_1737098430305",
    "FULL_NAME": "UF_CRM_1737098414068",
    "SHORT_NAME": "UF_CRM_1737098422264",
    "ADDR": "UF_CRM_1737098445351",
    "DIRECTOR_NAME": "UF_CRM_1737098484851",
    "DIRECTOR_POST": "UF_CRM_1737098491861",
    "EMPLOYEES": "UF_CRM_1737098498983",
    "REVENUE": "UF_CRM_1737098549301",
    "BRAND": "UF_CRM_1737098476975",
    "SITE": "UF_CRM_5DEF838D882A2",
    "CITY": "UF_CRM_1584876724",
}

FIXES = [
    {
        "cid": "4742",
        "title": "ООО \"Стоматологическая Клиника \"Дантистъ\" (Москва)",
        "uf": {
            "INN":           "7719429754",
            "OGRN":          "5157746032990",
            "FULL_NAME":     "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТЪ\"",
            "SHORT_NAME":    "ООО \"Стоматологическая Клиника \"Дантистъ\"",
            "ADDR":          "101000, город Москва, Архангельский пер., д. 7 стр. 1, пом. I комн. с 1 по 13",
            "DIRECTOR_NAME": "Халявка Валентина Владимировна",
            "DIRECTOR_POST": "Генеральный директор",
            "EMPLOYEES":     "7",
            "REVENUE":       "11472000",
            "BRAND":         "Belberry",
            "SITE":          "dentist-clinic.ru",
            "CITY":          "Москва",
        },
    },
    {
        "cid": "8360",
        "title": "ООО Стоматологическая Клиника \"Дантист\" (Серпухов)",
        "uf": {
            "INN":           "5043031718",
            "OGRN":          "1075043002968",
            "FULL_NAME":     "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТ\"",
            "SHORT_NAME":    "ООО Стоматологическая Клиника \"Дантист\"",
            "ADDR":          "142200, Московская область, город Серпухов, пр-д Мишина, д. 11, 111",
            "DIRECTOR_NAME": "Невский Александр Михайлович",
            "DIRECTOR_POST": "Генеральный директор",
            "EMPLOYEES":     "3",
            "REVENUE":       "15000000",
            "BRAND":         "Belberry",
            "CITY":          "Серпухов",
        },
    },
    {
        "cid": "8762",
        "title": "ООО \"Дантистъ\" (СПб)",
        "uf": {
            "INN":           "7816328303",
            "OGRN":          "1167847217812",
            "FULL_NAME":     "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"ДАНТИСТЪ\"",
            "SHORT_NAME":    "ООО \"Дантистъ\"",
            "ADDR":          "192212, Санкт-Петербург, Будапештская ул., д. 29 к. 1 литер а, пом. 5-н оф. 1",
            "DIRECTOR_NAME": "Гендлер Денис Борисович",
            "DIRECTOR_POST": "Генеральный директор",
            "EMPLOYEES":     "4",
            "REVENUE":       "15032000",
            "BRAND":         "Belberry",
            "CITY":          "Санкт-Петербург",
        },
    },
    {
        "cid": "9618",
        "title": "ООО \"Дантист\" (Калуга)",
        "uf": {
            "INN":           "4027063559",
            "OGRN":          "1044004401968",
            "FULL_NAME":     "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА \"ДАНТИСТ\"",
            "SHORT_NAME":    "ООО \"Дантист\"",
            "ADDR":          "248001, Калужская область, город Калуга, ул. Кирова, д. 47",
            "DIRECTOR_NAME": "Сидоренкова Наталия Евгеньевна",
            "DIRECTOR_POST": "Директор",
            "EMPLOYEES":     "13",
            "REVENUE":       "35407000",
            "BRAND":         "Belberry",
            "CITY":          "Калуга",
        },
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


def diff_line(label, before, after):
    eq = (str(before).strip() == str(after).strip())
    marker = " " if eq else "~"
    return f"     {marker} {label}: {before!r} -> {after!r}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cid", action="append")
    ap.add_argument("--skip-bp", action="store_true", help="не запускать bizproc.workflow.start 5614")
    args = ap.parse_args()
    fixes = [f for f in FIXES if (not args.cid or f["cid"] in args.cid)]
    log(f"fix_dantist_uf: {len(fixes)} cards (dry_run={args.dry_run})")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for f in fixes:
        cid = f["cid"]
        log(f"=== #{cid} {f['title']} ===")
        cur = call("crm.company.get", [("ID", cid)]).get("result") or {}
        if not cur:
            log(f"  !!! компания не найдена, пропускаю")
            continue

        # Backup
        bpath = BACKUP_DIR / f"{cid}_uf_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        bpath.write_text(json.dumps({"timestamp": datetime.now().isoformat(), "company": cur, "fix": f}, ensure_ascii=False, indent=2))
        log(f"  backup → {bpath.name}")

        # Build params: TITLE + UF
        params = [("ID", cid), ("fields[TITLE]", f["title"])]
        # diff print
        log(diff_line("TITLE", cur.get("TITLE"), f["title"]))
        for key, val in f["uf"].items():
            field = UF[key]
            params.append((f"fields[{field}]", str(val)))
            log(diff_line(f"{key}({field})", cur.get(field), val))

        if args.dry_run:
            log(f"  [DRY] would update {len(params)-1} fields")
            continue

        try:
            call("crm.company.update", params)
            log(f"  ✓ company updated")
        except Exception as e:
            log(f"  !!! company.update error: {e}")
            continue

        if not args.skip_bp:
            # Touch для триггера AUTO_EXECUTE BPs
            try:
                marker = f"\n[uf-fix {uuid.uuid4().hex[:8]}]"
                comments = (cur.get("COMMENTS") or "") + marker
                call("crm.company.update", [("ID", cid), ("fields[COMMENTS]", comments)])
                log(f"  ✓ touched")
            except Exception as e:
                log(f"  [warn] touch failed: {e}")

            try:
                r = call("bizproc.workflow.start", [
                    ("TEMPLATE_ID", "5614"),
                    ("DOCUMENT_ID[]", "crm"),
                    ("DOCUMENT_ID[]", "CCrmDocumentCompany"),
                    ("DOCUMENT_ID[]", f"COMPANY_{cid}"),
                ])
                log(f"  ✓ BP 5614 started: {r.get('result')}")
            except Exception as e:
                log(f"  [warn] BP start failed: {e}")

        # Verify
        v = call("crm.company.get", [("ID", cid)]).get("result") or {}
        log(f"  verify: TITLE={v.get('TITLE')!r}")
        log(f"           UF_INN={v.get(UF['INN'])!r}  UF_OGRN={v.get(UF['OGRN'])!r}")
        log(f"           UF_REVENUE={v.get(UF['REVENUE'])!r}  UF_DIRECTOR={v.get(UF['DIRECTOR_NAME'])!r}")


if __name__ == "__main__":
    main()
