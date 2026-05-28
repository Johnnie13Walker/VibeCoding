"""Роутер команд/интентов в workflow."""

from __future__ import annotations

from typing import Any

from cloudbot.orchestrator.search_state import load_search_state

COMMAND_ROUTES = {
    "/today": "day_briefing",
    "/brief": "day_briefing",
    "/day": "day_briefing",
    "/meetings": "meetings_summary",
    "/tasks": "tasks_summary",
    "/weather": "larisa_weather",
    "/search": "larisa_search",
    "/web": "larisa_search",
    "/find": "larisa_search",
    "/plan-day": "larisa_plan_day",
    "/plan": "larisa_plan_day",
    "/topics": "larisa_content_topics",
    "/posts": "larisa_content_topics",
    "/ideas": "larisa_content_topics",
    "/draft": "larisa_content_post",
    "/write-post": "larisa_content_post",
    "/harder": "larisa_content_post",
    "/softer": "larisa_content_post",
    "/business": "larisa_content_post",
    "/whoop": "whoop_report",
    "/health": "system_health",
    "/repair": "self_healing",
    "/sales": "sales_brief",
    "/pipeline": "sales_brief",
    "/risks": "sales_brief",
    "/focus-sales": "sales_brief",
    "/finance": "finance_summary",
    "/pnl": "pnl_analysis",
    "/cashflow": "cashflow_analysis",
    "/runway": "cashflow_analysis",
    "/expenses": "expense_structure_analysis",
    "/clients-profit": "client_profitability_analysis",
    "/ar": "receivables_analysis",
    "/ap": "payables_analysis",
    "/finance-risks": "finance_anomaly_scan",
    "/bitrixcheck": "bitrix_check",
}

INTENT_ROUTES = {
    "day_briefing": "day_briefing",
    "brief": "day_briefing",
    "plan_day": "larisa_plan_day",
    "weather": "larisa_weather",
    "search": "larisa_search",
    "web_search": "larisa_search",
    "web": "larisa_search",
    "meetings": "meetings_summary",
    "tasks": "tasks_summary",
    "whoop": "whoop_report",
    "topics": "larisa_content_topics",
    "content": "larisa_content_topics",
    "posts": "larisa_content_topics",
    "draft": "larisa_content_post",
    "post": "larisa_content_post",
    "harder": "larisa_content_post",
    "softer": "larisa_content_post",
    "business": "larisa_content_post",
    "health": "system_health",
    "repair": "self_healing",
    "sales": "sales_brief",
    "pipeline": "sales_brief",
    "risks": "sales_brief",
    "focus": "sales_brief",
    "finance": "finance_summary",
    "pnl": "pnl_analysis",
    "cashflow": "cashflow_analysis",
    "runway": "cashflow_analysis",
    "expenses": "expense_structure_analysis",
    "client_profitability": "client_profitability_analysis",
    "receivables": "receivables_analysis",
    "payables": "payables_analysis",
    "finance_risks": "finance_anomaly_scan",
    "bitrixcheck": "bitrix_check",
}

SEARCH_PREFIXES = (
    "кто",
    "что",
    "где",
    "когда",
    "как",
    "почему",
    "зачем",
    "сколько",
    "какой",
    "какая",
    "какие",
    "чей",
    "найди",
    "поищи",
    "поиск",
)

SEARCH_SIGNAL_TOKENS = (
    "счёт",
    "счет",
    "результат",
    "сыграл",
    "новост",
    "курс",
    "цска",
    "матч",
    "кто такой",
    "что такое",
)

NON_SEARCH_PREFIXES = (
    "привет",
    "здравствуйте",
    "спасибо",
    "ок",
    "хорошо",
    "ясно",
)

NON_SEARCH_PHRASES = (
    "как дела",
    "как ты",
    "ты на месте",
)

SEARCH_FOLLOWUP_TOKENS = frozenset(
    {
        "футбол",
        "футбольный",
        "хоккей",
        "хоккейный",
        "баскетбол",
        "баскетбольный",
    }
)


def _has_pending_search(message: dict[str, Any]) -> bool:
    chat_id = str(message.get("chat_id") or "").strip()
    user_id = str(message.get("user_id") or "").strip()
    return load_search_state(chat_id, user_id) is not None


def _looks_like_search_followup(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return normalized in SEARCH_FOLLOWUP_TOKENS


def _looks_like_search_query(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized or normalized.startswith("/"):
        return False
    if any(phrase in normalized for phrase in NON_SEARCH_PHRASES):
        return False
    if any(normalized.startswith(prefix) for prefix in NON_SEARCH_PREFIXES):
        return False
    if normalized.endswith("?"):
        return True
    if any(normalized.startswith(prefix) for prefix in SEARCH_PREFIXES):
        return True
    return any(token in normalized for token in SEARCH_SIGNAL_TOKENS)


def select_workflow(message: dict[str, Any]) -> str:
    command = str(message.get("command") or "").strip().lower()
    if command in COMMAND_ROUTES:
        return COMMAND_ROUTES[command]

    text = str(message.get("text") or "").strip().lower()
    token = text.split()[0] if text else ""
    if token in COMMAND_ROUTES:
        return COMMAND_ROUTES[token]

    intent = str(message.get("intent") or "").strip().lower()
    if intent in INTENT_ROUTES:
        return INTENT_ROUTES[intent]
    if _has_pending_search(message) and _looks_like_search_followup(text):
        return "larisa_search"
    if _looks_like_search_query(text):
        return "larisa_search"
    return "day_briefing"
