import json
from datetime import date
from typing import Any

from .db import build_upsert_sql, upsert


def write_day(
    conn,
    target_date: date,
    rows: dict[str, list[dict[str, Any]]],
    html: str,
    summary: dict,
    status: str = "done",
):
    report_row = {
        "report_date": target_date.isoformat(),
        "status": status,
        "html": html,
        "summary_json": json.dumps(summary, ensure_ascii=False),
        "generated_at": summary.get("generated_at"),
        "error_msg": None,
        "retry_count": 0,
    }
    report_sql = build_upsert_sql(
        "reports",
        list(report_row),
        ["report_date"],
        ["status", "html", "summary_json", "generated_at", "error_msg", "retry_count"],
    )
    with conn.cursor() as cursor:
        cursor.execute(report_sql, tuple(report_row.values()))

    counts = {"reports": 1}
    specs = [
        ("deals_snapshot", ["report_date", "deal_id"]),
        ("meetings", ["report_date", "meeting_id"]),
        ("manager_activity", ["report_date", "manager_id"]),
        ("kp_briefs", ["report_date", "item_id", "item_type"]),
    ]
    for table, conflict_cols in specs:
        table_rows = rows.get(table, [])
        if table_rows:
            update_cols = [col for col in table_rows[0] if col not in conflict_cols]
            counts[table] = upsert(conn, table, table_rows, conflict_cols, update_cols)
        else:
            counts[table] = 0
    return counts
