#!/usr/bin/env python3
"""Попытаться дозаполнить ИНН на компаниях, у которых реквизит создан, но пуст.

Алгоритм (по `fix_dantist_inns.py`):
  1. Touch компании через `crm.company.update fields[COMMENTS]=...` →
     это запускает BP 5614 (`AUTO_EXECUTE=2` на OnCrmCompanyUpdate).
  2. Подождать `--wait-bp` секунд (BP 5614 + DaData отрабатывают).
  3. Перечитать реквизиты → проверить, появился ли RQ_INN.

Источник списка целей: вкладка `Дубли компаний (скоринг)` + requisites.json дамп.
По дефолту тянет список из дампов `/opt/openclaw/data/empty_co/`. Список можно
переопределить через `--ids 170,2002,...`.

Запуск (VPS):
  BITRIX_STATE_PATH=/opt/openclaw/state/bitrix_app/install.latest.json \\
  /opt/openclaw/venvs/crm_company_merge/bin/python \\
  /opt/openclaw/repos/vibecoding/belberry/bitrix24/empty_companies_score/scripts/enrich_no_inn_via_bp5614.py \\
  [--ids 170,2002,...] [--dry-run] [--wait-bp 60] [--limit N]

См. также: `project_belberry_dup_detection.md` — урок про guard BP 5614.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from empty_companies_score.bitrix_client import BitrixClient  # noqa: E402
from empty_companies_score.config import BITRIX_STATE, PORTAL_BASE  # noqa: E402

DATA_DIR = Path("/opt/openclaw/data/empty_co")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", help="ручной список company_id через запятую (иначе из дампов)")
    p.add_argument("--limit", type=int, help="ограничить первыми N")
    p.add_argument("--wait-bp", type=int, default=60, help="сек ожидания BP 5614 после touch")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    bx = BitrixClient(BITRIX_STATE)
    targets = _resolve_targets(args.ids)
    if args.limit:
        targets = targets[: args.limit]

    print(f"[{_ts()}] targets: {len(targets)}; wait-bp={args.wait_bp}s; dry={args.dry_run}")

    # Снимок реквизитов ДО
    before = {cid: _list_requisites(bx, cid) for cid in targets}
    for cid in targets:
        title = _company_title(bx, cid)
        print(f"  BEFORE #{cid} ({title!r}): {[(r['ID'], r.get('RQ_INN'), r.get('RQ_OGRN'), r.get('RQ_OGRNIP')) for r in before[cid]]}")

    if args.dry_run:
        print(f"[{_ts()}] dry-run: touch и проверка пропущены")
        return 0

    # Touch всех целей (последовательно, ~1 r/s)
    print(f"[{_ts()}] touching {len(targets)} companies ...")
    for cid in targets:
        try:
            _touch(bx, cid)
            print(f"  TOUCH #{cid} ok")
        except Exception as e:  # noqa: BLE001
            print(f"  TOUCH #{cid} FAIL: {e}")

    # Ждём BP 5614 + DaData
    print(f"[{_ts()}] waiting {args.wait_bp}s for BP 5614 + DaData ...")
    time.sleep(args.wait_bp)

    # Проверяем результат
    print(f"[{_ts()}] checking results ...")
    filled, still_empty, errors = [], [], []
    for cid in targets:
        try:
            after = _list_requisites(bx, cid)
        except Exception as e:  # noqa: BLE001
            errors.append({"cid": cid, "error": str(e)})
            continue
        has_inn = any((r.get("RQ_INN") or "").strip() for r in after)
        snapshot = [(r["ID"], r.get("RQ_INN"), r.get("RQ_OGRN"), r.get("RQ_OGRNIP")) for r in after]
        if has_inn:
            inn = next((r.get("RQ_INN") for r in after if (r.get("RQ_INN") or "").strip()), "")
            filled.append({"cid": cid, "inn": inn, "snapshot": snapshot})
            print(f"  OK    #{cid} → RQ_INN={inn} | {snapshot}")
        else:
            still_empty.append({"cid": cid, "snapshot": snapshot})
            print(f"  EMPTY #{cid} (BP guard? DaData miss?) | {snapshot}")

    print()
    print(json.dumps({
        "filled": len(filled),
        "still_empty": len(still_empty),
        "errors": errors,
        "filled_ids": [f["cid"] for f in filled],
        "still_empty_ids": [s["cid"] for s in still_empty],
    }, ensure_ascii=False, indent=2))
    return 0


def _resolve_targets(ids_arg: str | None) -> list[str]:
    if ids_arg:
        return [s.strip() for s in ids_arg.split(",") if s.strip()]
    # из дампов: те же 48 компаний (реквизит есть, но RQ_INN ни в одном из них пустой)
    reqs = json.loads((DATA_DIR / "requisites.json").read_text())
    by_co: dict[str, list[dict]] = {}
    for r in reqs:
        cid = str(r.get("ENTITY_ID") or "")
        if cid:
            by_co.setdefault(cid, []).append(r)
    targets = [cid for cid, rs in by_co.items() if not any((r.get("RQ_INN") or "").strip() for r in rs)]
    targets.sort(key=int)
    return targets


def _list_requisites(bx: BitrixClient, company_id: str) -> list[dict]:
    out: list[dict] = []
    last_id = 0
    while True:
        params = [
            ("filter[ENTITY_TYPE_ID]", "4"),
            ("filter[ENTITY_ID]", company_id),
            ("filter[>ID]", str(last_id)),
            ("order[ID]", "ASC"),
            ("start", "-1"),
        ]
        for f in ("ID", "RQ_INN", "RQ_OGRN", "RQ_OGRNIP", "RQ_KPP", "RQ_COMPANY_NAME"):
            params.append(("select[]", f))
        resp = bx.call("crm.requisite.list", params)
        batch = resp.get("result", [])
        if not batch:
            return out
        out.extend(batch)
        last_id = int(batch[-1]["ID"])
        if len(batch) < 50:
            return out


def _company_title(bx: BitrixClient, company_id: str) -> str:
    r = bx.call("crm.company.get", [("id", company_id)])
    if r.get("error_description") == "Not found":
        return "<deleted>"
    c = r.get("result") or {}
    return (c.get("TITLE") or "").strip()


def _touch(bx: BitrixClient, company_id: str) -> None:
    g = bx.call("crm.company.get", [("id", company_id)])
    company = g.get("result") or {}
    if not company:
        raise RuntimeError(f"company #{company_id} not found")
    comments = company.get("COMMENTS") or ""
    marker = f"\n[touch {uuid.uuid4().hex[:8]}]"
    bx.call(
        "crm.company.update",
        [("ID", company_id), ("fields[COMMENTS]", comments + marker)],
    )


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
