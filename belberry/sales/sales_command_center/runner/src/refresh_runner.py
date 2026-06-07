"""Частый refresh данных за СЕГОДНЯ для дашбордов/вкладок — БЕЗ LLM/Telegram/отчёта.

Собирает текущий день (сделки/звонки/встречи/активность) и пишет в дашборд-таблицы
(deals_snapshot + manager_activity + meetings + kp_briefs + call_hourly), СОХРАНЯЯ
уже сделанные LLM-разборы встреч (analysis_json/транскрипт не затираются —
write_flow_day их preserve'ит). Идемпотентно. Cron каждые 20 мин в рабочее время.

    python -m src.refresh_runner
    python -m src.refresh_runner 2026-06-06
"""

import sys
from datetime import date, datetime

from . import bx_client
from .backfill import write_flow_day
from .collect import collect_day
from .db import connect, upsert
from .timeutil import MSK
from .transform import build_db_rows


def refresh(target: date, conn, bx=None) -> dict[str, int]:
    raw = collect_day(target, bx)
    now = datetime.now(MSK)
    rows = build_db_rows(raw, target, now)

    # flow-таблицы + meetings (с сохранением analysis_json/транскрипта) + reports-заглушка.
    write_flow_day(conn, target, rows, now)

    # deals_snapshot за сегодня — заменяем целиком (закрытые/ушедшие сделки выпадают).
    rd = target.isoformat()
    ds = rows.get("deals_snapshot", [])
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM deals_snapshot WHERE report_date = %s", (rd,))
    if ds:
        cols = [c for c in ds[0] if c not in ("report_date", "deal_id")]
        upsert(conn, "deals_snapshot", ds, ["report_date", "deal_id"], cols)
    conn.commit()

    return {
        "deals_snapshot": len(ds),
        "manager_activity": len(rows.get("manager_activity", [])),
        "meetings": len(rows.get("meetings", [])),
    }


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = date.fromisoformat(argv[0]) if argv else datetime.now(MSK).date()
    bx_client.ensure_token_fresh()
    conn = connect()
    try:
        res = refresh(target, conn)
    finally:
        conn.close()
    print(f"[REFRESH] {target}: {res}", flush=True)


if __name__ == "__main__":
    main()
