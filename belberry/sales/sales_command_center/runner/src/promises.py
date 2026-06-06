"""Петля контроля: вчера обещали -> сегодня выполнили."""

import json
from datetime import date
from typing import Any

from .deltas import _previous_report_date
from .timeutil import prev_working_day


def compute_promises_loop(conn, target: date, current_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    # «Вчера» = тот же якорь, что у дельт: реальный последний отчёт в БД.
    # prev_working_day — только фолбэк для первого прогона (отчётов ещё нет).
    previous_date = _previous_report_date(conn, target) or prev_working_day(target)
    promises = _read_previous_promises(conn, previous_date)
    if not promises:
        return {
            "previous_date": previous_date.isoformat(),
            "items": [],
            "message": "нет структурных обещаний за предыдущий день",
        }
    previous_stages = _read_previous_stages(conn, previous_date)
    return evaluate_promises(promises, current_rows, previous_stages, target, previous_date=previous_date)


def evaluate_promises(
    promises: list[dict[str, Any]],
    current_rows: dict[str, list[dict[str, Any]]],
    previous_stages: dict[int, str],
    target: date,
    *,
    previous_date: date | None = None,
) -> dict[str, Any]:
    current_stages = {
        int(row["deal_id"]): row.get("stage")
        for row in current_rows.get("deals_snapshot", [])
        if row.get("deal_id") is not None
    }
    kp_deals = {
        int(row["deal_id"])
        for row in current_rows.get("kp_briefs", [])
        if row.get("deal_id") is not None and row.get("item_type") == "kp"
    }
    brief_deals = {
        int(row["deal_id"])
        for row in current_rows.get("kp_briefs", [])
        if row.get("deal_id") is not None and row.get("item_type") == "brief"
    }

    items = []
    for promise in promises:
        deal_id = _to_int(promise.get("deal_id"))
        signals = _signals(deal_id, current_stages, previous_stages, kp_deals, brief_deals)
        status_key, status = _status(signals, promise.get("deadline"), target)
        items.append(
            {
                **promise,
                "deal_id": deal_id,
                "status_key": status_key,
                "status": status,
                "signals": signals,
            }
        )
    return {
        "previous_date": previous_date.isoformat() if previous_date else None,
        "items": items,
        "message": None if items else "нет структурных обещаний за предыдущий день",
    }


def _read_previous_promises(conn, previous_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT meeting_id, deal_id, manager_id, analysis_json
            FROM meetings
            WHERE report_date = %s
            """,
            (previous_date.isoformat(),),
        )
        rows = cursor.fetchall()

    promises = []
    for row in rows:
        meeting_id, deal_id, manager_id, analysis_json = _row_values(
            row,
            ("meeting_id", "deal_id", "manager_id", "analysis_json"),
        )
        analysis = _json_load(analysis_json)
        step = analysis.get("next_step") if isinstance(analysis, dict) else None
        if not isinstance(step, dict) or not step.get("what"):
            continue
        promises.append(
            {
                "source_meeting_id": meeting_id,
                "deal_id": _to_int(deal_id),
                "manager_id": _to_int(manager_id),
                "promise": str(step.get("what") or "").strip(),
                "owner": str(step.get("who") or "").strip() or None,
                "deadline": step.get("deadline"),
            }
        )
    return promises


def _read_previous_stages(conn, previous_date: date) -> dict[int, str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT deal_id, stage
            FROM deals_snapshot
            WHERE report_date = %s
            """,
            (previous_date.isoformat(),),
        )
        rows = cursor.fetchall()
    out = {}
    for row in rows:
        deal_id, stage = _row_values(row, ("deal_id", "stage"))
        deal_id = _to_int(deal_id)
        if deal_id is not None:
            out[deal_id] = stage
    return out


def _signals(
    deal_id: int | None,
    current_stages: dict[int, str],
    previous_stages: dict[int, str],
    kp_deals: set[int],
    brief_deals: set[int],
) -> list[str]:
    if deal_id is None:
        return []
    signals = []
    if deal_id in current_stages and deal_id in previous_stages and current_stages[deal_id] != previous_stages[deal_id]:
        signals.append("стадия изменилась")
    if deal_id in kp_deals:
        signals.append("КП отправлено")
    if deal_id in brief_deals:
        signals.append("бриф создан")
    return signals


def _status(signals: list[str], deadline: Any, target: date) -> tuple[str, str]:
    if signals:
        return "done", "✅ выполнено"
    overdue = _is_overdue(deadline, target)
    if overdue is True:
        return "overdue", "❌ просрочено"
    if overdue is False:
        return "on_time", "⏳ в срок"
    return "unknown", "❓ нужно проверить"


def _is_overdue(deadline: Any, target: date) -> bool | None:
    if deadline in (None, ""):
        return None
    text = str(deadline).strip().lower()
    try:
        return date.fromisoformat(text[:10]) < target
    except ValueError:
        pass
    if "вчера" in text:
        return True
    if any(token in text for token in ("сегодня", "завтра", "на неделе", "понедельник", "вторник", "среда", "четверг", "пятница")):
        return False
    return None


def _row_values(row: Any, keys: tuple[str, ...]) -> tuple[Any, ...]:
    if isinstance(row, dict):
        return tuple(row.get(key) for key in keys)
    return tuple(row[index] for index, _ in enumerate(keys))


def _json_load(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
