"""Точка входа агента Ларисы Ивановны."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .commands import (
    build_get_content_post_command,
    build_get_content_topics_command,
    build_get_day_brief_command,
    build_get_meetings_command,
    build_get_midday_replan_command,
    build_get_tasks_command,
    build_get_weather_command,
    build_get_web_search_command,
    build_plan_day_command,
)
from .config import DEFAULT_CONFIG, LarisaIvanovnaConfig, WEEKDAY_LABELS
from .policy import LarisaIvanovnaPolicy
from .providers import (
    BitrixCalendarProvider,
    OpenMeteoWeatherProvider,
    SharedTelegramRouteProvider,
    TodoistTasksProvider,
)
from .schemas.brief import DayBriefRequest
from .workflows.daily_brief import DailyBriefWorkflowDeps
from .workflows.content_topics import ContentTopicsWorkflowDeps
from .workflows.midday_replan import MiddayReplanWorkflowDeps
from .workflows.tasks import TasksWorkflowDeps
from .workflows.meetings import MeetingsWorkflowDeps
from .workflows.weather import WeatherWorkflowDeps


class LarisaIvanovnaAgentError(RuntimeError):
    """Ошибка контура Ларисы Ивановны."""


@dataclass(frozen=True)
class LarisaDependencies:
    calendar_provider: Any
    tasks_provider: Any
    weather_provider: Any
    telegram_provider: Any
    content_topics_deps: Any | None = None


class LarisaIvanovnaAgent:
    def __init__(
        self,
        *,
        config: LarisaIvanovnaConfig = DEFAULT_CONFIG,
        dependencies: LarisaDependencies,
    ) -> None:
        self.config = config
        self.policy = LarisaIvanovnaPolicy(config)
        self.dependencies = dependencies
        self.registry = self._build_registry()

    def _build_registry(self) -> dict[str, dict[str, object]]:
        daily_brief_deps = DailyBriefWorkflowDeps(
            calendar_provider=self.dependencies.calendar_provider,
            tasks_provider=self.dependencies.tasks_provider,
            weather_provider=self.dependencies.weather_provider,
        )
        commands = [
            build_get_content_topics_command(
                self.dependencies.content_topics_deps or ContentTopicsWorkflowDeps.from_env()
            ),
            build_get_content_post_command(
                self.dependencies.content_topics_deps or ContentTopicsWorkflowDeps.from_env()
            ),
            build_get_day_brief_command(daily_brief_deps),
            build_get_meetings_command(
                MeetingsWorkflowDeps(
                    calendar_provider=self.dependencies.calendar_provider,
                )
            ),
            build_get_tasks_command(
                TasksWorkflowDeps(
                    tasks_provider=self.dependencies.tasks_provider,
                )
            ),
            build_get_weather_command(
                WeatherWorkflowDeps(
                    weather_provider=self.dependencies.weather_provider,
                )
            ),
            build_get_web_search_command(),
            build_get_midday_replan_command(
                MiddayReplanWorkflowDeps(
                    tasks_provider=self.dependencies.tasks_provider,
                )
            ),
            build_plan_day_command(daily_brief_deps),
        ]

        registry: dict[str, dict[str, object]] = {}
        for command in commands:
            registry[str(command["name"])] = command
            for alias in command["aliases"]:
                registry[str(alias)] = command
        return registry

    def execute(
        self,
        command_name: str,
        payload: Any,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        command = self.registry.get(str(command_name))
        if command is None:
            raise LarisaIvanovnaAgentError(f"Команда {command_name} не зарегистрирована.")
        handler = command["handler"]
        return handler(payload, context)

    def dispatch_to_telegram(
        self,
        command_name: str,
        payload: Any,
        *,
        context: dict[str, Any] | None = None,
        chat_id: str = "",
        send_reply: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        result = self.execute(command_name, payload, context=context)
        if result.get("should_send") is False:
            return {
                **result,
                "delivery": {
                    "delivered": False,
                    "skipped": True,
                    "reason": str(result.get("skip_reason") or "suppressed"),
                },
            }
        delivery = self.dependencies.telegram_provider.send(
            str(result.get("text") or ""),
            chat_id=chat_id,
            send_reply=send_reply,
        )
        return {
            **result,
            "delivery": delivery,
        }


def build_larisa_agent_from_env(env_data: dict[str, str] | None = None) -> LarisaIvanovnaAgent:
    env_payload = dict(env_data or os.environ)
    dependencies = LarisaDependencies(
        calendar_provider=BitrixCalendarProvider(env_data=env_payload),
        tasks_provider=TodoistTasksProvider(env_data=env_payload),
        weather_provider=OpenMeteoWeatherProvider(),
        telegram_provider=SharedTelegramRouteProvider(env_data=env_payload),
        content_topics_deps=ContentTopicsWorkflowDeps.from_env(env_payload),
    )
    return LarisaIvanovnaAgent(
        config=DEFAULT_CONFIG,
        dependencies=dependencies,
    )


def _now_moscow() -> datetime:
    return datetime.now(ZoneInfo(DEFAULT_CONFIG.timezone))


def _build_day_brief_request(date_value: str = "") -> DayBriefRequest:
    if date_value:
        current = datetime.strptime(date_value, "%d.%m.%Y").replace(tzinfo=ZoneInfo(DEFAULT_CONFIG.timezone))
    else:
        current = _now_moscow()
    return DayBriefRequest(
        date_msk=current.strftime("%d.%m.%Y"),
        weekday_msk=WEEKDAY_LABELS[current.weekday()],
    )


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Larisa Ivanovna Agent")
    parser.add_argument(
        "--command",
        default="get_day_brief",
        choices=(
            "get_content_topics",
            "get_content_post",
            "get_day_brief",
            "get_meetings",
            "get_tasks",
            "plan_day",
            "get_weather",
            "get_midday_replan",
        ),
        help="Команда контура Ларисы Ивановны",
    )
    parser.add_argument("--send", action="store_true", help="Отправить результат в Telegram")
    parser.add_argument("--chat-id", default="", help="Явный chat_id для Telegram")
    parser.add_argument("--date", default="", help="Дата в формате DD.MM.YYYY")
    parser.add_argument("--city", default="", help="Город для погодного блока")
    parser.add_argument("--hour", type=int, default=-1, help="Час МСК для midday replan")
    parser.add_argument(
        "--period",
        default="day",
        choices=("day", "week", "all"),
        help="Период для контентных тем",
    )
    parser.add_argument("--topic", type=int, default=0, help="Номер темы для генерации черновика поста")
    parser.add_argument(
        "--tone",
        default="default",
        choices=("default", "harder", "softer", "business"),
        help="Тональность черновика поста",
    )
    return parser


def _build_cli_payload(command_name: str, args: argparse.Namespace) -> Any:
    if command_name == "get_content_topics":
        request = _build_day_brief_request(args.date)
        return {
            "date_msk": request.date_msk,
            "period_key": args.period,
        }
    if command_name == "get_content_post":
        request = _build_day_brief_request(args.date)
        return {
            "date_msk": request.date_msk,
            "period_key": args.period,
            "topic_index": args.topic,
            "tone": args.tone,
        }
    if command_name in {"get_day_brief", "plan_day"}:
        return _build_day_brief_request(args.date)
    if command_name == "get_weather":
        request = _build_day_brief_request(args.date)
        return {
            "date_msk": request.date_msk,
            "city": args.city or DEFAULT_CONFIG.default_city,
        }
    if command_name == "get_midday_replan":
        request = _build_day_brief_request(args.date)
        hour_value = args.hour if int(args.hour) >= 0 else _now_moscow().hour
        return {"date_msk": request.date_msk, "now_hour_msk": hour_value}
    if command_name in {"get_meetings", "get_tasks"}:
        request = _build_day_brief_request(args.date)
        return {"date_msk": request.date_msk}
    raise LarisaIvanovnaAgentError(f"CLI не знает, как собрать payload для {command_name}.")


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    try:
        agent = build_larisa_agent_from_env()
        payload = _build_cli_payload(args.command, args)
        if args.send:
            result = agent.dispatch_to_telegram(args.command, payload, chat_id=args.chat_id)
        else:
            result = agent.execute(args.command, payload)
    except Exception as error:  # noqa: BLE001
        print(f"LARISA AGENT ERROR: {error}", file=sys.stderr)
        return 1

    print(str(result.get("text") or ""))
    if args.send:
        print(json.dumps(result.get("delivery") or {}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
