"""Общие adapter-функции для workflow Ларисы Ивановны."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.larisa_ivanovna import LarisaIvanovnaAgentError, build_larisa_agent_from_env
from apps.larisa_ivanovna.config import DEFAULT_CONFIG, WEEKDAY_LABELS
from apps.larisa_ivanovna.schemas.brief import DayBriefRequest
from apps.larisa_ivanovna.timezone import ensure_moscow_datetime

WORKFLOW_BY_COMMAND = {
    "get_content_post": "larisa_content_post",
    "get_content_topics": "larisa_content_topics",
    "get_day_brief": "day_briefing",
    "get_meetings": "meetings_summary",
    "get_tasks": "tasks_summary",
    "get_weather": "larisa_weather",
    "get_web_search": "larisa_search",
    "plan_day": "larisa_plan_day",
}


def build_day_brief_request(now: datetime | None = None) -> DayBriefRequest:
    current = ensure_moscow_datetime(now)
    return DayBriefRequest(
        date_msk=current.strftime("%d.%m.%Y"),
        weekday_msk=WEEKDAY_LABELS[current.weekday()],
    )


def build_content_topics_payload(context: dict[str, Any]) -> dict[str, str]:
    text = _extract_message_text(context)
    period_key = "day"
    if any(token in text for token in ("недел", "week", "7d")):
        period_key = "week"
    elif any(token in text for token in ("весь", "all", "истори")):
        period_key = "all"
    request = build_day_brief_request()
    return {
        "date_msk": request.date_msk,
        "period_key": period_key,
    }


def build_content_post_payload(context: dict[str, Any]) -> dict[str, object]:
    text = _extract_message_text(context)
    period_key = build_content_topics_payload(context)["period_key"]
    topic_index = _extract_topic_index(text)
    tone = _extract_tone(text)
    request = build_day_brief_request()
    return {
        "date_msk": request.date_msk,
        "period_key": period_key,
        "topic_index": topic_index,
        "tone": tone,
    }


def build_search_payload(context: dict[str, Any]) -> dict[str, str]:
    message = context.get("message") if isinstance(context, dict) else {}
    if not isinstance(message, dict):
        return {"query": "", "chat_id": "", "user_id": ""}
    query = extract_message_tail(context) or str(message.get("text") or "").strip()
    return {
        "query": query,
        "chat_id": str(message.get("chat_id") or "").strip(),
        "user_id": str(message.get("user_id") or "").strip(),
    }


def _extract_message_text(context: dict[str, Any]) -> str:
    message = context.get("message") if isinstance(context, dict) else {}
    if not isinstance(message, dict):
        return ""
    return str(message.get("text") or "").lower()


def extract_message_tail(context: dict[str, Any]) -> str:
    message = context.get("message") if isinstance(context, dict) else {}
    if not isinstance(message, dict):
        return ""
    text = str(message.get("text") or "").strip()
    command = str(message.get("command") or "").strip().lower()
    if not text:
        return ""
    if command and text.lower().startswith(command):
        return text[len(command) :].strip()
    parts = text.split(maxsplit=1)
    if parts and parts[0].startswith("/"):
        return parts[1].strip() if len(parts) > 1 else ""
    return text


def _extract_topic_index(text: str) -> int:
    for token in text.split():
        if token.isdigit():
            return int(token)
    return 0


def _extract_tone(text: str) -> str:
    first = text.split()[0] if text else ""
    mapping = {
        "/harder": "harder",
        "harder": "harder",
        "/softer": "softer",
        "softer": "softer",
        "/business": "business",
        "business": "business",
    }
    return mapping.get(first, "default")


def run_larisa_command(
    command_name: str,
    *,
    context: dict[str, Any],
    payload: Any,
) -> dict[str, Any]:
    workflow_name = WORKFLOW_BY_COMMAND[command_name]
    try:
        agent = build_larisa_agent_from_env()
        result = agent.execute(command_name, payload, context=context)
    except LarisaIvanovnaAgentError as error:
        return {
            "ok": False,
            "workflow": workflow_name,
            "agent_id": DEFAULT_CONFIG.agent_id,
            "text": f"Не удалось выполнить команду Ларисы Ивановны: {error}",
            "error": str(error),
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "workflow": workflow_name,
            "agent_id": DEFAULT_CONFIG.agent_id,
            "text": f"Критическая ошибка контура Ларисы Ивановны: {error}",
            "error": str(error),
        }

    return {
        "ok": True,
        "workflow": workflow_name,
        "agent_id": DEFAULT_CONFIG.agent_id,
        "text": str(result.get("text") or ""),
        "payload": result.get("payload"),
    }
