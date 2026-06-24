"""Превентив (#5): сканирует ЖИВЫЕ сделки воронки «Продажи» на процессные красные флаги
(те же системные провалы, что находит аудит) — ДО того, как сделка умерла. Пишет снимок
в deal_risk_flags → блок «Риск процесса» в Алертах. Ловит тёплые сделки на грани слива.

Запуск:  python -m src.audit_preventive --once   (cron раз в день)
"""

from __future__ import annotations

import json
import sys

from . import audit_engine, bx_client

STAGE_NAMES = {
    "C10:NEW": "Квалификация", "C10:PREPAYMENT_INVOIC": "Подготовка БРИФа",
    "C10:EXECUTING": "Подготовка КП", "C10:UC_4SJOE4": "Защита КП",
    "C10:FINAL_INVOICE": "Получить решение", "C10:UC_RJK0KE": "Получить реквизиты",
    "C10:UC_KC7195": "Согласование договора", "C10:UC_755Z64": "Ожидаем оплату",
}
ADVANCED = {"C10:EXECUTING", "C10:UC_4SJOE4", "C10:FINAL_INVOICE", "C10:UC_RJK0KE", "C10:UC_KC7195", "C10:UC_755Z64"}


def _risk_flags(sig: dict) -> list[str]:
    flags = []
    if sig["kp_sent"] and sig["kp_cards"] == 0:
        flags.append("КП без карточки в системе")
    if sig["kp_via_pitch"]:
        flags.append("КП через сторонний сервис")
    if sig["kp_sent"] and not sig["had_defense"] and sig["stage_id"] in ADVANCED:
        flags.append("КП не защищено перед ЛПР")
    if sig["stage_id"] == "C10:UC_4SJOE4" and not sig["had_defense"]:
        flags.append("Стадия «Защита КП», а защиты не было")
    if sig["briefs_total"] >= 3:
        flags.append("Стрельба по площадям (3+ брифа)")
    if sig["handover_count"] >= 2:
        flags.append("Передача между менеджерами без контекста")
    return flags


def scan() -> list[dict]:
    """Открытые C10 сделки с риск-флагами."""
    deals, start = [], 0
    while True:
        r = bx_client.call("crm.deal.list", {
            "filter": {"CATEGORY_ID": 10, "CLOSED": "N"},
            "select": ["ID", "TITLE", "STAGE_ID", "ASSIGNED_BY_ID"], "order": {"ID": "ASC"}, "start": start,
        })
        deals += r.get("result", [])
        if "next" in r:
            start = r["next"]
        else:
            break
    out = []
    for d in deals:
        did = int(d["ID"])
        ctx = audit_engine.collect_deal_context(did)
        if not ctx:
            continue
        flags = _risk_flags(audit_engine.compute_signals(ctx))
        if not flags:
            continue
        out.append({
            "deal_id": did, "title": d.get("TITLE"),
            "stage_label": STAGE_NAMES.get(d.get("STAGE_ID"), d.get("STAGE_ID")),
            "manager_id": int(d.get("ASSIGNED_BY_ID") or 0) or None,
            "flags": flags, "severity": "critical" if len(flags) >= 2 else "warning",
        })
    return out


def main() -> int:
    from . import db
    risky = scan()
    print(f"живых сделок с риск-флагами: {len(risky)}")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM deal_risk_flags")  # снимок: полностью перезаписываем
            for r in risky:
                cur.execute(
                    "INSERT INTO deal_risk_flags (deal_id, title, stage_label, manager_id, flags, severity, checked_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s, now())",
                    (r["deal_id"], r["title"], r["stage_label"], r["manager_id"],
                     json.dumps(r["flags"], ensure_ascii=False), r["severity"]),
                )
            conn.commit()
    for r in risky:
        print(f"  [{r['severity']}] {r['deal_id']} {r['title']} ({r['stage_label']}): {', '.join(r['flags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
