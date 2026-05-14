"""
fix_dantist_inns.py — точечная правка ошибочных ИНН в кластере ДАНТИСТЪ.

4 карточки получили один и тот же ИНН 5250071606 (Кстово, Нижегородская обл.) по
ошибке через BP 5614, хотя это разные клиники в разных регионах. Скрипт меняет
реквизит на правильный ИНН и триггерит BP 5614 для подтягивания корректных
КПП/ОГРН/юр.названия/адреса через DaData.

Шаги для каждой карточки:
  1. Снимок текущего состояния (company + requisites) → JSON-бэкап.
  2. Найти текущий реквизит с RQ_INN=5250071606.
  3. crm.requisite.delete старого.
  4. crm.requisite.add нового с RQ_INN=<правильный>, PRESET_ID=1, NAME="Реквизиты ЮЛ".
  5. Touch компании (uuid-маркер в COMMENTS) → BP 5614 AUTO_EXECUTE=2 запустится.
  6. Подождать N секунд, verify: новый реквизит должен получить RQ_OGRN.

Запуск:
  bash shared/scripts/bitrix-sync-state.sh
  python belberry/bitrix24/fix_dantist_inns.py --dry-run
  python belberry/bitrix24/fix_dantist_inns.py
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

BITRIX_STATE = Path(
    os.environ.get(
        "BITRIX_STATE_PATH",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
    )
)
BACKUP_DIR = Path(__file__).parent / "backups" / "dantist_inn_fix"
WRONG_INN = "5250071606"
WAIT_BP_S = 30  # ждать BP 5614 после touch

FIXES = [
    {"cid": "4742", "label": "Москва, dentist-clinic.ru",  "new_inn": "7719429754"},
    {"cid": "8360", "label": "Серпухов, dantist-s.ru",      "new_inn": "5043031718"},
    {"cid": "8762", "label": "СПб, dantistspb.ru",          "new_inn": "7816328303"},
    {"cid": "9618", "label": "Калуга, dantist40.ru",        "new_inn": "4027063559"},
]


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def call(method, params, max_tries=6):
    s = json.loads(BITRIX_STATE.read_text())["payload"]
    endpoint = s["auth[client_endpoint]"].rstrip("/")
    token = s["auth[access_token]"]
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
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
                time.sleep(min(30, 2 ** attempt))
                continue
            raise RuntimeError(f"{method} HTTP {e.code}: {body[:200]}") from e
        except Exception:
            if attempt < max_tries - 1:
                time.sleep(min(20, 2 ** attempt))
                continue
            raise


def get_company(cid):
    return call("crm.company.get", [("ID", cid)]).get("result") or {}


def list_requisites(cid):
    return call(
        "crm.requisite.list",
        [
            ("filter[ENTITY_TYPE_ID]", "4"),
            ("filter[ENTITY_ID]", cid),
            ("start", "-1"),
        ],
    ).get("result", []) or []


def add_requisite(cid, inn, dry):
    fields = {
        "ENTITY_TYPE_ID": 4,
        "ENTITY_ID": int(cid),
        "PRESET_ID": 1,
        "NAME": "Реквизиты ЮЛ" if len(inn) == 10 else "Реквизиты ИП",
        "RQ_INN": inn,
    }
    params = []
    for k, v in fields.items():
        params.append((f"fields[{k}]", str(v)))
    if dry:
        return None
    r = call("crm.requisite.add", params)
    return r.get("result")


def delete_requisite(req_id, dry):
    if dry:
        return
    call("crm.requisite.delete", [("ID", str(req_id))])


def touch_company(cid, dry):
    if dry:
        return
    c = get_company(cid)
    comments = c.get("COMMENTS") or ""
    marker = f"\n[touch {uuid.uuid4().hex[:8]}]"
    new_comments = f"{comments}{marker}"
    call(
        "crm.company.update",
        [("ID", cid), ("fields[COMMENTS]", new_comments)],
    )


def save_backup(item, snapshot):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = BACKUP_DIR / f"{item['cid']}_{ts}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return path


def process(item, dry, wait_bp):
    cid = item["cid"]
    new_inn = item["new_inn"]
    label = item["label"]
    log(f"=== #{cid} ({label}) → новый ИНН {new_inn} ===")

    company = get_company(cid)
    if not company:
        log(f"  !!! company #{cid} not found — skip")
        return {"cid": cid, "status": "company_not_found"}

    reqs_before = list_requisites(cid)
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "company": company,
        "requisites_before": reqs_before,
        "fix": item,
    }
    bpath = save_backup(item, snapshot)
    log(f"  backup → {bpath.name}")

    # Найти реквизит с неверным ИНН
    wrong_reqs = [r for r in reqs_before if (r.get("RQ_INN") or "").strip() == WRONG_INN]
    if not wrong_reqs:
        log(f"  WARN: реквизит с ИНН {WRONG_INN} НЕ найден на карточке. Реквизиты сейчас: {[(r['ID'], r.get('RQ_INN')) for r in reqs_before]}")
        return {"cid": cid, "status": "no_wrong_inn", "current": [(r['ID'], r.get('RQ_INN')) for r in reqs_before]}

    log(f"  найден неверный реквизит(ы): {[(r['ID'], r.get('RQ_INN')) for r in wrong_reqs]}")
    log(f"  {'[DRY] ' if dry else ''}delete старого + add нового с ИНН {new_inn}...")

    new_req_id = None
    try:
        # Добавим новый ПЕРЕД удалением старого (atomicity-lite: если add не сработает, старый сохранится).
        new_req_id = add_requisite(cid, new_inn, dry)
        log(f"  {'[DRY] ' if dry else ''}new requisite created: {new_req_id}")

        for wr in wrong_reqs:
            delete_requisite(wr["ID"], dry)
            log(f"  {'[DRY] ' if dry else ''}deleted old requisite #{wr['ID']} (RQ_INN={wr.get('RQ_INN')})")

        # Touch для триггера BP 5614
        touch_company(cid, dry)
        log(f"  {'[DRY] ' if dry else ''}company touched")

    except Exception as e:
        log(f"  !!! ERROR: {e}")
        return {"cid": cid, "status": "error", "error": str(e), "new_req_id": new_req_id, "backup": str(bpath)}

    if dry:
        return {"cid": cid, "status": "dry_ok", "would_add_inn": new_inn, "would_delete_reqs": [r["ID"] for r in wrong_reqs]}

    # Verify: ждём BP, потом проверяем заполнение
    log(f"  waiting {wait_bp}s for BP 5614 to populate KPP/OGRN/name...")
    time.sleep(wait_bp)
    reqs_after = list_requisites(cid)
    enriched = None
    for r in reqs_after:
        if (r.get("RQ_INN") or "").strip() == new_inn:
            enriched = r
            break
    if not enriched:
        return {"cid": cid, "status": "verify_no_new_req", "after": [(r['ID'], r.get('RQ_INN')) for r in reqs_after]}

    bp_filled = bool((enriched.get("RQ_OGRN") or enriched.get("RQ_OGRNIP") or "").strip())
    log(f"  verify: req#{enriched['ID']} RQ_INN={enriched.get('RQ_INN')} RQ_KPP={enriched.get('RQ_KPP')} RQ_OGRN={enriched.get('RQ_OGRN')} RQ_COMPANY_NAME={enriched.get('RQ_COMPANY_NAME')!r}")
    return {
        "cid": cid,
        "status": "ok" if bp_filled else "ok_but_bp_pending",
        "new_req_id": enriched["ID"],
        "new_inn": enriched.get("RQ_INN"),
        "rq_ogrn": enriched.get("RQ_OGRN") or enriched.get("RQ_OGRNIP"),
        "rq_company_name": enriched.get("RQ_COMPANY_NAME"),
        "rq_addr": enriched.get("RQ_ADDR"),
        "backup": str(bpath),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cid", action="append", help="только указанные ID")
    ap.add_argument("--wait-bp", type=int, default=WAIT_BP_S, help=f"сек ожидания BP 5614 (default {WAIT_BP_S})")
    args = ap.parse_args()

    fixes = FIXES
    if args.cid:
        fixes = [f for f in FIXES if f["cid"] in args.cid]
    log(f"fix_dantist_inns: start (dry_run={args.dry_run}, cards={len(fixes)})")

    results = []
    for it in fixes:
        try:
            results.append(process(it, args.dry_run, args.wait_bp))
        except Exception as e:
            log(f"  fatal on #{it['cid']}: {e}")
            results.append({"cid": it["cid"], "status": "fatal", "error": str(e)})

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"_summary_{datetime.now().strftime('%Y%m%dT%H%M%S')}{'_dry' if args.dry_run else ''}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    log(f"summary → {out}")

    print("\n=== SUMMARY ===")
    for r in results:
        cid = r["cid"]
        st = r.get("status")
        if st == "ok":
            print(f"  ✓ #{cid}: INN={r['new_inn']}  OGRN={r['rq_ogrn']}  name={r['rq_company_name']!r}")
        elif st == "ok_but_bp_pending":
            print(f"  ~ #{cid}: INN={r['new_inn']}  BP ещё не отработал, проверь через минуту")
        elif st == "dry_ok":
            print(f"  [dry] #{cid}: would set INN={r['would_add_inn']}, delete reqs {r['would_delete_reqs']}")
        else:
            print(f"  ! #{cid}: {st} — {r}")


if __name__ == "__main__":
    main()
