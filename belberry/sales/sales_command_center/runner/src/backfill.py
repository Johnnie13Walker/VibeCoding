"""Backfill истории потоковых метрик отдела продаж.

Перегоняет по каждому рабочему дню заданного диапазона ТОЛЬКО потоковые таблицы
(manager_activity, meetings без LLM-анализа, kp_briefs), наполняя в т.ч. новые
колонки won/cold/incoming. НЕ трогает deals_snapshot (снимок открытой воронки за
прошлое не восстановим — Bitrix хранит только текущее состояние) и не
перезаписывает существующие отчёты (reports). Идемпотентно: повторный прогон
обновляет те же строки.

Запуск (на проде, с DATABASE_URL в окружении):
    python -m src.backfill 2026-01-01 2026-06-04
    python -m src.backfill --dry-run 2026-05-15 2026-05-15   # без записи, печатает счётчики
"""

import sys
from datetime import date, datetime, timedelta

from . import bx_client
from .collect import collect_flow_day
from .db import connect, upsert
from .timeutil import MSK, prev_working_day
from .transform import build_db_rows

_FLOW_TABLES = [
    ("manager_activity", ["report_date", "manager_id"]),
    ("meetings", ["report_date", "meeting_id"]),
    ("kp_briefs", ["report_date", "item_id", "item_type"]),
]

# Колонки meetings, которые backfill НЕ должен затирать (их наполняет боевой
# раннер LLM-разбором; backfill историю не анализирует).
_MEETINGS_PRESERVE = {"analysis_json", "transcript_url", "transcript_text", "transcript_ok", "analysis_status"}

# Таблицы без ценных данных — чистим за день перед вставкой, чтобы не оставались
# строки менеджеров, выпавших при смене логики (остаточные строки).
_REBUILD_TABLES = ("manager_activity", "kp_briefs")


def _is_workday(d: date) -> bool:
    return d.weekday() < 5


def _ensure_report_stub(conn, report_date: str, now: datetime) -> None:
    """Создаёт строку reports только если её ещё нет (FK для дочерних таблиц).
    Реальные отчёты (status='done', html) не затирает."""
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO reports (report_date, status, generated_at, retry_count) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (report_date) DO NOTHING",
            (report_date, "backfill", now.isoformat() if hasattr(now, "isoformat") else now, 0),
        )


def write_flow_day(conn, target: date, rows: dict, now: datetime) -> dict[str, int]:
    rd = target.isoformat()
    _ensure_report_stub(conn, rd, now)
    # Чистим пересобираемые таблицы за этот день (убрать остаточные строки).
    with conn.cursor() as cursor:
        for table in _REBUILD_TABLES:
            cursor.execute(f'DELETE FROM "{table}" WHERE report_date = %s', (rd,))
    counts: dict[str, int] = {}
    for table, conflict_cols in _FLOW_TABLES:
        table_rows = rows.get(table, [])
        if not table_rows:
            counts[table] = 0
            continue
        update_cols = [
            c
            for c in table_rows[0]
            if c not in conflict_cols and not (table == "meetings" and c in _MEETINGS_PRESERVE)
        ]
        counts[table] = upsert(conn, table, table_rows, conflict_cols, update_cols)
    return counts


def backfill_range(start: date, end: date, conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    totals = {"days": 0, "manager_activity": 0, "meetings": 0, "kp_briefs": 0}
    cur = start
    while cur <= end:
        if _is_workday(cur):
            raw = collect_flow_day(cur, bx)
            now = datetime.now(MSK)
            rows = build_db_rows(raw, cur, now)
            ma = len(rows.get("manager_activity", []))
            mt = len(rows.get("meetings", []))
            kb = len(rows.get("kp_briefs", []))
            print(
                f"{cur} flow: manager_activity={ma} meetings={mt} kp_briefs={kb} "
                f"won={len(raw['won_deals'])} created={len(raw['deals_created'])}",
                flush=True,
            )
            if not dry_run and conn is not None:
                write_flow_day(conn, cur, rows, now)
                conn.commit()
            totals["days"] += 1
            totals["manager_activity"] += ma
            totals["meetings"] += mt
            totals["kp_briefs"] += kb
        cur += timedelta(days=1)
    return totals


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    positional = [a for a in argv if not a.startswith("--")]
    start = date.fromisoformat(positional[0]) if positional else date(2026, 1, 1)
    end = date.fromisoformat(positional[1]) if len(positional) > 1 else prev_working_day()

    conn = None
    if not dry_run:
        bx_client.ensure_token_fresh()
        conn = connect()
    try:
        totals = backfill_range(start, end, conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    mode = "DRY-RUN" if dry_run else "WRITTEN"
    print(f"\n[{mode}] {start}..{end}: {totals}", flush=True)


if __name__ == "__main__":
    main()
