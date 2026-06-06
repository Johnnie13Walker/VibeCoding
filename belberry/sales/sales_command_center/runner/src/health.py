"""Детерминированный health-score дня для отчёта продаж."""

from typing import Any

DAILY_MEETING_NORM = 4


def compute_health_score(
    manager_activity: list[dict[str, Any]],
    meetings: list[dict[str, Any]],
    stale: dict[str, list[dict[str, Any]]],
    *,
    daily_meeting_norm: int = DAILY_MEETING_NORM,
) -> dict[str, Any]:
    oper_pct = _average_oper_percent(manager_activity)
    meeting_score_pct = _average_meeting_score_percent(meetings)
    meeting_volume_pct = _meeting_volume_percent(len(meetings), daily_meeting_norm)
    stale_rows = [item for rows in (stale or {}).values() for item in rows]
    risk_penalty = _risk_penalty(stale_rows)

    raw_score = (
        0.35 * oper_pct
        + 0.30 * meeting_score_pct
        + 0.15 * meeting_volume_pct
        - risk_penalty
    )
    score = max(0, min(100, round(raw_score)))
    level = "green" if score >= 70 else "amber" if score >= 40 else "red"

    return {
        "score": score,
        "level": level,
        "label": "здоровье дня",
        "formula": (
            "0.35*Опер активных + 0.30*балл встреч + "
            "0.15*факт встреч - штраф риска"
        ),
        "components": {
            "oper_percent": round(oper_pct),
            "meeting_score_percent": round(meeting_score_pct),
            "meeting_volume_percent": round(meeting_volume_pct),
            "risk_penalty": round(risk_penalty, 1),
            "stale_count": len(stale_rows),
            "risk_money": round(sum(float(item.get("opportunity") or 0) for item in stale_rows), 2),
        },
    }


def _average_oper_percent(manager_activity: list[dict[str, Any]]) -> float:
    scores = [
        float(item.get("operational_score") or 0)
        for item in manager_activity
        if not item.get("away") and item.get("operational_score") is not None
    ]
    return sum(scores) / len(scores) / 10 * 100 if scores else 0.0


def _average_meeting_score_percent(meetings: list[dict[str, Any]]) -> float:
    scores = []
    for meeting in meetings:
        analysis = meeting.get("analysis") or {}
        score = _to_float(analysis.get("score"))
        if score is not None:
            scores.append(score)
    return sum(scores) / len(scores) / 10 * 100 if scores else 0.0


def _meeting_volume_percent(meetings_count: int, daily_meeting_norm: int) -> float:
    if daily_meeting_norm <= 0:
        return 0.0
    return min(100.0, meetings_count / daily_meeting_norm * 100)


def _risk_penalty(stale_rows: list[dict[str, Any]]) -> float:
    risk_money = sum(float(item.get("opportunity") or 0) for item in stale_rows)
    count_penalty = min(15.0, len(stale_rows) * 3.0)
    money_penalty = min(10.0, risk_money / 1_000_000 * 5.0)
    return min(25.0, count_penalty + money_penalty)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
