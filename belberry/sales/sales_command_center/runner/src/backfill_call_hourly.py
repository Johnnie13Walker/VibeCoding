"""Точечный бэкафилл call_hourly (heatmap «когда берут трубку»).

Per рабочий день: collect_voximplant → почасовая агрегация (час МСК) → перезапись
call_hourly за этот день. Не трогает другие таблицы — нулевой blast radius.
Идемпотентно (delete+insert по дню). Без LLM/Telegram.

    python -m src.backfill_call_hourly 2025-11-01 2026-06-04
    python -m src.backfill_call_hourly --dry-run 2026-05-01 2026-05-31
"""

import sys
from datetime import date, timedelta

from . import bx_client
from .collect import collect_voximplant
from .db import connect, upsert
from .transform import aggregate_calls_hourly


def _is_workday(d: date) -> bool:
    return d.weekday() < 5


def _rows_for_day(bx, day: date) -> list[dict]:
    calls = collect_voximplant(day, bx)
    agg = aggregate_calls_hourly(calls)
    return [
        {
            "report_date": day.isoformat(),
            "manager_id": uid,
            "hour": hour,
            "dials": s.get("dials", 0),
            "answered": s.get("answered", 0),
            "calls60": s.get("calls60", 0),
        }
        for (uid, hour), s in agg.items()
    ]


def backfill_range(start: date, end: date, conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    totals = {"days": 0, "rows": 0}
    cur = start
    while cur <= end:
        if _is_workday(cur):
            rows = _rows_for_day(bx, cur)
            if not dry_run and conn is not None:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM call_hourly WHERE report_date = %s", (cur.isoformat(),))
                if rows:
                    upsert(conn, "call_hourly", rows, ["report_date", "manager_id", "hour"], ["dials", "answered", "calls60"])
                conn.commit()
            print(f"{cur} rows={len(rows)}", flush=True)
            totals["days"] += 1
            totals["rows"] += len(rows)
        cur += timedelta(days=1)
    return totals


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    positional = [a for a in argv if not a.startswith("--")]
    start = date.fromisoformat(positional[0])
    end = date.fromisoformat(positional[1]) if len(positional) > 1 else start
    bx_client.ensure_token_fresh()
    conn = None if dry_run else connect()
    try:
        totals = backfill_range(start, end, conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] call_hourly {start}..{end}: {totals}", flush=True)


if __name__ == "__main__":
    main()
