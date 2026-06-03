from __future__ import annotations

from datetime import date
from typing import Any


METRIC_LABELS = {
    "meetings": "Встречи проведены",
    "dials": "Наборы",
    "connect_percent": "Конверсия дозвона",
    "deals_created": "Новые сделки",
    "kp_sent": "КП",
}


def metrics_from_rows(rows: dict[str, list[dict[str, Any]]]) -> dict[str, float]:
    managers = rows.get("manager_activity") or []
    dials = sum(int(item.get("dials_total") or 0) for item in managers)
    answered = sum(int(item.get("calls_answered") or 0) for item in managers)
    kp_rows = [item for item in rows.get("kp_briefs") or [] if item.get("item_type") == "kp"]
    kp_sent = len(kp_rows) or sum(int(item.get("kp_sent") or 0) for item in managers)
    return {
        "meetings": float(len(rows.get("meetings") or [])),
        "dials": float(dials),
        "connect_percent": round(answered / dials * 100, 1) if dials else 0.0,
        "deals_created": float(sum(int(item.get("deals_created_count") or 0) for item in managers)),
        "kp_sent": float(kp_sent),
    }


def _db_metrics(conn, report_date: date) -> dict[str, float]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              (SELECT count(*) FROM meetings WHERE report_date = %s) AS meetings,
              COALESCE(sum(dials_total), 0) AS dials,
              COALESCE(sum(calls_answered), 0) AS answered,
              COALESCE(sum(deals_created_count), 0) AS deals_created,
              COALESCE(sum(kp_sent), 0) AS kp_sent
            FROM manager_activity
            WHERE report_date = %s
            """,
            (report_date.isoformat(), report_date.isoformat()),
        )
        row = cursor.fetchone()
    if not row:
        return {}
    if isinstance(row, dict):
        meetings = row.get("meetings")
        dials = row.get("dials")
        answered = row.get("answered")
        deals_created = row.get("deals_created")
        kp_sent = row.get("kp_sent")
    else:
        meetings, dials, answered, deals_created, kp_sent = row
    dials = float(dials or 0)
    answered = float(answered or 0)
    return {
        "meetings": float(meetings or 0),
        "dials": dials,
        "connect_percent": round(answered / dials * 100, 1) if dials else 0.0,
        "deals_created": float(deals_created or 0),
        "kp_sent": float(kp_sent or 0),
    }


def _previous_report_date(conn, target: date) -> date | None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT max(report_date) FROM reports WHERE report_date < %s",
            (target.isoformat(),),
        )
        row = cursor.fetchone()
    value = row.get("max") if isinstance(row, dict) else row[0] if row else None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)) if value else None


def metric_delta(current: float, previous: float | None) -> dict[str, Any]:
    if previous is None:
        return {"value": current, "previous": None, "delta": None, "delta_percent": None, "trend": "flat"}
    delta = round(current - previous, 1)
    delta_percent = round(delta / previous * 100) if previous else None
    trend = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return {
        "value": current,
        "previous": previous,
        "delta": delta,
        "delta_percent": delta_percent,
        "trend": trend,
    }


def compute_deltas(conn, target: date, rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    current = metrics_from_rows(rows)
    previous_date = _previous_report_date(conn, target)
    previous = _db_metrics(conn, previous_date) if previous_date else {}
    return {
        "previous_report_date": previous_date.isoformat() if previous_date else None,
        "metrics": {
            key: {
                "label": METRIC_LABELS[key],
                **metric_delta(value, previous.get(key) if previous else None),
            }
            for key, value in current.items()
        },
    }


def delta_label(metric: dict[str, Any]) -> str | None:
    delta = metric.get("delta")
    if delta is None:
        return None
    if metric.get("delta_percent") is not None:
        sign = "+" if metric["delta_percent"] > 0 else ""
        return f"{sign}{metric['delta_percent']}%"
    sign = "+" if delta > 0 else ""
    if float(delta).is_integer():
        delta = int(delta)
    return f"{sign}{delta}"
