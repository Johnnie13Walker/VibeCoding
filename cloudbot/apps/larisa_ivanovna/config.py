"""Конфигурация и идентичность агента Ларисы Ивановны."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

MSK_TIMEZONE: Final[str] = "Europe/Moscow"

ALLOWED_SCOPES: Final[tuple[str, ...]] = (
    "calendar",
    "tasks",
    "weather",
    "search",
    "telegram",
    "day_planning",
    "content",
)

BLOCKED_SCOPES: Final[tuple[str, ...]] = (
    "crm",
    "deals",
    "sales",
    "sales_analytics",
    "finance",
    "commercial_reporting",
    "devops",
)

COMMAND_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "get_day_brief": ("/today", "/brief", "/day"),
    "get_meetings": ("/meetings",),
    "get_tasks": ("/tasks",),
    "get_weather": ("/weather",),
    "get_web_search": ("/search", "/web", "/find"),
    "plan_day": ("/plan-day", "/plan"),
    "get_content_topics": ("/topics", "/posts", "/ideas"),
    "get_content_post": ("/draft", "/write-post"),
    "get_content_post_harder": ("/harder",),
    "get_content_post_softer": ("/softer",),
    "get_content_post_business": ("/business",),
}

WEEKDAY_LABELS: Final[dict[int, str]] = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}

@dataclass(frozen=True)
class TelegramRouteConfig:
    route_key: str = "larisa-ivanovna"
    bot_token_env_candidates: tuple[str, ...] = (
        "LARISA_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
    )
    chat_id_env_candidates: tuple[str, ...] = (
        "LARISA_TELEGRAM_CHAT_ID",
        "TELEGRAM_CHAT_ID",
    )
    dry_run_env_candidates: tuple[str, ...] = (
        "LARISA_TELEGRAM_DRY_RUN",
        "TELEGRAM_DRY_RUN",
    )
    parse_mode: str = "HTML"


@dataclass(frozen=True)
class LarisaIvanovnaConfig:
    agent_id: str = "larisa_ivanovna"
    display_name: str = "Лариса Ивановна"
    timezone: str = MSK_TIMEZONE
    legacy_workflows: tuple[str, ...] = (
        "day_briefing",
        "meetings_summary",
        "tasks_summary",
    )
    default_city: str = "Москва"
    focus_preferred_windows: tuple[str, ...] = (
        "10:00-11:00",
        "12:00-13:00",
        "15:00-16:00",
    )
    allowed_scopes: tuple[str, ...] = ALLOWED_SCOPES
    blocked_scopes: tuple[str, ...] = BLOCKED_SCOPES
    telegram: TelegramRouteConfig = TelegramRouteConfig()


DEFAULT_CONFIG = LarisaIvanovnaConfig()
