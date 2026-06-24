"""Петля отслеживания возврата (#3): через FOLLOWUP_DAYS дней после «вернуть в работу»
проверяет, СРАБОТАЛ ли возврат — двинулась ли сделка. Пишет результат в deal_audits
(followup_status: progressed|in_progress|stalled + note). Превращает аудит из «красивого
отчёта» в управление: видно, какие возвраты дошли до дела, а какие зависли снова.

Запуск:  python -m src.audit_followup --once   (cron раз в день)
"""

from __future__ import annotations

import os
import sys

from . import bx_client

FOLLOWUP_DAYS = int(os.environ.get("AUDIT_FOLLOWUP_DAYS", "7"))
TASK_DONE_STATUSES = {"5"}  # 5 = завершена


def _classify(audit_id, deal_id, task_id, return_stage, returned_at) -> tuple[str, str]:
    deal = bx_client.call("crm.deal.get", {"id": deal_id}).get("result") or {}
    stage = deal.get("STAGE_ID", "")
    sem = deal.get("STAGE_SEMANTIC_ID")  # P/S/F
    moved = bool(return_stage) and stage != return_stage
    won = sem == "S" or stage.endswith(":WON")
    lost = sem == "F" or stage.endswith(":LOSE")

    task_done = False
    if task_id:
        t = bx_client.call("tasks.task.get", {"taskId": task_id, "select": ["STATUS"]}).get("result", {}).get("task", {})
        task_done = str(t.get("status") or "") in TASK_DONE_STATUSES

    # активность после возврата (звонок/дело/комментарий)
    acts = bx_client.call("crm.activity.list", {
        "filter": {"OWNER_ID": deal_id, "OWNER_TYPE_ID": 2, ">CREATED": str(returned_at)},
        "select": ["ID"],
    }).get("result", [])
    new_activity = len(acts) > 0

    if won:
        return "progressed", "Сделка выиграна 🎉"
    if lost:
        return "stalled", "Сделка снова ушла в отвал — возврат не сработал."
    if task_done:
        return "progressed", "Задача из возврата выполнена."
    if moved:
        return "progressed", f"Стадия сдвинулась: {return_stage} → {stage}."
    if new_activity:
        return "in_progress", "Есть контакт после возврата, но стадия не сдвинулась — дожимают."
    return "stalled", f"За {FOLLOWUP_DAYS} дней ноль движения — возврат завис, нужен ручной разбор."


def main() -> int:
    from . import db
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, deal_id, task_id, return_stage, returned_at FROM deal_audits "
                "WHERE returned_to_work AND followup_at IS NULL "
                "AND returned_at IS NOT NULL AND returned_at < now() - interval '%s days' "
                "ORDER BY returned_at LIMIT 50",
                (FOLLOWUP_DAYS,),
            )
            rows = cur.fetchall()
        print(f"к проверке (возврат >{FOLLOWUP_DAYS}д назад): {len(rows)}")
        for aid, deal_id, task_id, return_stage, returned_at in rows:
            try:
                status, note = _classify(aid, deal_id, task_id, return_stage, returned_at)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {deal_id}: {e}")
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE deal_audits SET followup_status=%s, followup_note=%s, followup_at=now() WHERE id=%s",
                    (status, note, aid),
                )
                conn.commit()
            print(f"  • deal {deal_id}: {status} — {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
