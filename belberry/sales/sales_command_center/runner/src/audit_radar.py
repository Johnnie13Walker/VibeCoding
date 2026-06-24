"""Радар застрявших сделок: находит сделки воронки «Продажи» БЕЗ дальнейших дел
(нет открытых активностей/задач И нет активных карточек встреч/брифов/КП) и ставит
по ним авто-аудит (source='auto'). Воркер аудита разберёт их, как обычные задания —
сделки всплывут на /audit и в Алертах. Превращает аудит из кнопки в радар (улучшение #1).

Дедуп: не аудитим сделку, по которой аудит уже был за последние RADAR_DEDUP_DAYS дней.
Лимит RADAR_MAX_PER_RUN на прогон — чтобы не залить LLM в первый день.

Запуск:  python -m src.audit_radar --once
"""

from __future__ import annotations

import os
import sys

from . import bx_client

CATEGORY = 10  # воронка «Продажи»
RADAR_DEDUP_DAYS = int(os.environ.get("RADAR_DEDUP_DAYS", "30"))
RADAR_MAX_PER_RUN = int(os.environ.get("RADAR_MAX_PER_RUN", "10"))


def _open_deals() -> list[dict]:
    out, start = [], 0
    while True:
        r = bx_client.call("crm.deal.list", {
            "filter": {"CATEGORY_ID": CATEGORY, "CLOSED": "N"},
            "select": ["ID", "TITLE", "STAGE_ID"], "order": {"ID": "ASC"}, "start": start,
        })
        out += r.get("result", [])
        if "next" in r:
            start = r["next"]
        else:
            break
    return out


def _deals_with_open_activity(ids: set[int]) -> set[int]:
    """ID сделок, у которых есть незавершённое дело/задача (активность COMPLETED=N)."""
    have, start = set(), 0
    while True:
        r = bx_client.call("crm.activity.list", {
            "filter": {"OWNER_TYPE_ID": 2, "COMPLETED": "N"},
            "select": ["ID", "OWNER_ID"], "order": {"ID": "ASC"}, "start": start,
        })
        res = r.get("result", [])
        for a in res:
            oid = int(a.get("OWNER_ID") or 0)
            if oid in ids:
                have.add(oid)
        if "next" in r:
            start = r["next"]
        else:
            break
    return have


def _has_active_bp(deal_id: int) -> bool:
    """Есть ли активная (не SUCCESS/FAIL) карточка встречи/брифа/КП — тоже «дело»."""
    for etid in (1048, 1056, 1106):
        r = bx_client.call("crm.item.list", {
            "entityTypeId": etid, "filter": {"parentId2": deal_id}, "select": ["id", "stageId"],
        })
        for it in (r.get("result") or {}).get("items", []):
            st = it.get("stageId", "")
            if not (st.endswith(":SUCCESS") or st.endswith(":FAIL")):
                return True
    return False


def find_stuck_deals() -> list[dict]:
    deals = _open_deals()
    ids = {int(d["ID"]) for d in deals}
    with_act = _deals_with_open_activity(ids)
    stuck = []
    for d in deals:
        did = int(d["ID"])
        if did in with_act:
            continue
        if _has_active_bp(did):
            continue
        stuck.append(d)
    return stuck


def enqueue(conn, deals: list[dict]) -> int:
    """Ставит авто-аудиты по застрявшим, минус дедуп; не больше RADAR_MAX_PER_RUN."""
    queued = 0
    with conn.cursor() as cur:
        for d in deals:
            if queued >= RADAR_MAX_PER_RUN:
                break
            did = int(d["ID"])
            cur.execute(
                "SELECT 1 FROM deal_audits WHERE deal_id=%s AND created_at > now() - interval '%s days' LIMIT 1",
                (did, RADAR_DEDUP_DAYS),
            )
            if cur.fetchone():
                continue  # недавно уже аудитили
            cur.execute(
                "INSERT INTO deal_audits (deal_id, source, requested_by) VALUES (%s, 'auto', NULL)",
                (did,),
            )
            conn.commit()
            queued += 1
            print(f"  ▶ авто-аудит: {did} {d.get('TITLE')} [{d.get('STAGE_ID')}]")
    return queued


def main() -> int:
    from . import db
    stuck = find_stuck_deals()
    print(f"застрявших без дел: {len(stuck)}")
    with db.connect() as conn:
        n = enqueue(conn, stuck)
    print(f"поставлено авто-аудитов: {n} (дедуп {RADAR_DEDUP_DAYS}д, лимит {RADAR_MAX_PER_RUN})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
