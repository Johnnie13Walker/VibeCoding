from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from apps.larisa_ivanovna.agent import LarisaDependencies, LarisaIvanovnaAgent
from apps.larisa_ivanovna.config import DEFAULT_CONFIG
from apps.larisa_ivanovna.providers import (
    CalendarProvider,
    NullCalendarProvider,
    NullTelegramProvider,
    NullTasksProvider,
    NullWeatherProvider,
    OpenMeteoWeatherProvider,
    SharedTelegramRouteProvider,
    TasksProvider,
    WeatherProvider,
)
from apps.larisa_ivanovna.providers.calendar_provider import BitrixCalendarProvider
from apps.larisa_ivanovna.providers.tasks_provider import TodoistTasksProvider
from apps.larisa_ivanovna.schemas.brief import DayBriefRequest, WeatherSnapshot
from apps.larisa_ivanovna.schemas.calendar import CalendarDaySnapshot, CalendarEvent, CreateCalendarEventInput
from apps.larisa_ivanovna.workflows.content_topics import ContentTopicsWorkflowDeps
from apps.larisa_ivanovna.schemas.task import TaskDaySnapshot, TaskItem
from cloudbot.bot.telegram.commands import extract_command
from cloudbot.orchestrator.router import COMMAND_ROUTES, select_workflow
from cloudbot.workflows import day_briefing


class StaticCalendarProvider(CalendarProvider):
    def __init__(self, snapshot: CalendarDaySnapshot) -> None:
        self.snapshot = snapshot

    def get_day_snapshot(self, date_msk: str) -> CalendarDaySnapshot:
        return self.snapshot

    def create_event(self, payload):  # type: ignore[override]
        return {
            "created": True,
            "event": CalendarEvent(
                id="new-1",
                title=payload.title,
                start_at_msk=payload.start_at_msk,
                end_at_msk=payload.end_at_msk or payload.start_at_msk,
            ),
        }


class FailingCalendarProvider(CalendarProvider):
    def get_day_snapshot(self, date_msk: str) -> CalendarDaySnapshot:
        raise RuntimeError("calendar offline")

    def create_event(self, payload):  # type: ignore[override]
        raise RuntimeError("calendar offline")


class StaticTasksProvider(TasksProvider):
    def __init__(self, snapshot: TaskDaySnapshot) -> None:
        self.snapshot = snapshot

    def get_day_snapshot(self, date_msk: str) -> TaskDaySnapshot:
        return self.snapshot


class StaticWeatherProvider(WeatherProvider):
    def __init__(self, snapshot: WeatherSnapshot) -> None:
        self.snapshot = snapshot

    def get_weather(self, date_msk: str, city: str) -> WeatherSnapshot:
        return self.snapshot


class FailingWeatherProvider(WeatherProvider):
    def get_weather(self, date_msk: str, city: str) -> WeatherSnapshot:
        raise RuntimeError("weather offline")


class LarisaAgentTests(unittest.TestCase):
    def _build_agent(
        self,
        *,
        calendar_provider: CalendarProvider | None = None,
        tasks_provider: TasksProvider | None = None,
        weather_provider: WeatherProvider | None = None,
    ) -> LarisaIvanovnaAgent:
        return LarisaIvanovnaAgent(
            config=DEFAULT_CONFIG,
            dependencies=LarisaDependencies(
                calendar_provider=calendar_provider or NullCalendarProvider(),
                tasks_provider=tasks_provider or NullTasksProvider(),
                weather_provider=weather_provider or NullWeatherProvider(),
                telegram_provider=NullTelegramProvider(),
                content_topics_deps=ContentTopicsWorkflowDeps.from_env(),
            ),
        )

    def test_registry_contains_expected_commands(self) -> None:
        agent = self._build_agent()

        for key in (
            "get_day_brief",
            "get_web_search",
            "get_midday_replan",
            "/today",
            "/brief",
            "/day",
            "/meetings",
            "/tasks",
            "/weather",
            "/search",
            "/plan-day",
            "/plan",
            "get_content_topics",
            "/topics",
            "/posts",
            "/ideas",
        ):
            self.assertIn(key, agent.registry)

    def test_content_topics_builds_digest_from_git_and_status(self) -> None:
        with TemporaryDirectory() as engineer_tmp, TemporaryDirectory() as architect_tmp:
            engineer_root = Path(engineer_tmp)
            architect_root = Path(architect_tmp)
            subprocess.run(["git", "init"], cwd=engineer_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=engineer_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=engineer_root, check=True)

            target_file = engineer_root / "apps" / "larisa_ivanovna" / "agent.py"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("# test\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=engineer_root, check=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Добавить контур копирайтера",
                    "--date",
                    "2026-04-02T09:15:00+03:00",
                ],
                cwd=engineer_root,
                check=True,
                capture_output=True,
                text=True,
            )
            fake_gh = engineer_root / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env python3\n"
                "print('[{\"number\": 17, \"title\": \"Добавить Telegram-маршрут для контента\", \"updatedAt\": \"2026-04-02T09:40:00+03:00\", \"headRefName\": \"codex/content\"}]')\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            status_dir = architect_root / "docs"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "STATUS.md").write_text(
                "\n".join(
                    [
                        "# STATUS",
                        "- Дата и время: `2026-04-02 09:30 MSK`",
                        "- Сценарий: `manual`",
                        "- Что сделано: добавлен отдельный контур копирайтера и подготовлен Telegram-маршрут.",
                    ]
                ),
                encoding="utf-8",
            )

            agent = LarisaIvanovnaAgent(
                config=DEFAULT_CONFIG,
                dependencies=LarisaDependencies(
                    calendar_provider=NullCalendarProvider(),
                    tasks_provider=NullTasksProvider(),
                    weather_provider=NullWeatherProvider(),
                    telegram_provider=NullTelegramProvider(),
                    content_topics_deps=ContentTopicsWorkflowDeps(
                        engineer_root=engineer_root,
                        architect_root=architect_root,
                        tasks_provider=StaticTasksProvider(
                            TaskDaySnapshot(
                                date_msk="02.04.2026",
                                tasks_for_today=(TaskItem(id="1", title="Подготовить контур копирайтера", bucket="today"),),
                                source_available=True,
                            )
                        ),
                        gh_binary=str(fake_gh),
                    ),
                ),
            )

            result = agent.execute("get_content_topics", {"date_msk": "02.04.2026", "period_key": "day"})
            text = result["text"]
            self.assertIn("Темы для постов", text)
            self.assertRegex(text, r"1\. Почему .+")
            self.assertIn("контур копирайтера", text)
            self.assertIn("Telegram-маршрут", text)
            self.assertIn("Подготовить контур копирайтера", text)
            self.assertIn("PR #17", text)

    def test_content_topics_from_env_handles_shallow_engineer_root(self) -> None:
        engineer_root = Path("/workspace/codex-base")

        deps = ContentTopicsWorkflowDeps.from_env(
            {"CLOUDBOT_ENGINEER_ROOT": str(engineer_root)}
        )

        self.assertEqual(deps.engineer_root, engineer_root)
        self.assertEqual(deps.architect_root, engineer_root.parent / "architect")

    def test_content_post_builds_draft_for_selected_topic(self) -> None:
        with TemporaryDirectory() as engineer_tmp, TemporaryDirectory() as architect_tmp:
            engineer_root = Path(engineer_tmp)
            architect_root = Path(architect_tmp)
            subprocess.run(["git", "init"], cwd=engineer_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=engineer_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=engineer_root, check=True)
            target_file = engineer_root / "infra" / "orchestrator" / "workflows" / "copywriter.sh"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=engineer_root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Добавить nightly digest", "--date", "2026-04-02T12:00:00+03:00"],
                cwd=engineer_root,
                check=True,
                capture_output=True,
                text=True,
            )
            status_dir = architect_root / "docs"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "STATUS.md").write_text(
                "\n".join(
                    [
                        "# STATUS",
                        "- Дата и время: `2026-04-02 12:10 MSK`",
                        "- Что сделано: добавлен nightly digest для тем постов.",
                    ]
                ),
                encoding="utf-8",
            )
            fake_gh = engineer_root / "gh"
            fake_gh.write_text("#!/usr/bin/env python3\nprint('[]')\n", encoding="utf-8")
            fake_gh.chmod(0o755)
            agent = LarisaIvanovnaAgent(
                config=DEFAULT_CONFIG,
                dependencies=LarisaDependencies(
                    calendar_provider=NullCalendarProvider(),
                    tasks_provider=NullTasksProvider(),
                    weather_provider=NullWeatherProvider(),
                    telegram_provider=NullTelegramProvider(),
                    content_topics_deps=ContentTopicsWorkflowDeps(
                        engineer_root=engineer_root,
                        architect_root=architect_root,
                        tasks_provider=StaticTasksProvider(
                            TaskDaySnapshot(
                                date_msk="02.04.2026",
                                tasks_for_today=(TaskItem(id="1", title="Проверить digest", bucket="today"),),
                                source_available=True,
                            )
                        ),
                        gh_binary=str(fake_gh),
                    ),
                ),
            )

            result = agent.execute("get_content_post", {"date_msk": "02.04.2026", "period_key": "day", "topic_index": 1})
            self.assertIn("Черновик по теме 1", result["text"])
            self.assertIn("Хук:", result["text"])
            self.assertIn("Фактура", result["text"])

    def test_content_post_supports_business_tone(self) -> None:
        with TemporaryDirectory() as engineer_tmp, TemporaryDirectory() as architect_tmp:
            engineer_root = Path(engineer_tmp)
            architect_root = Path(architect_tmp)
            subprocess.run(["git", "init"], cwd=engineer_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=engineer_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=engineer_root, check=True)
            target_file = engineer_root / "docs" / "playbook.md"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("контур\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=engineer_root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Описать playbook", "--date", "2026-04-02T13:00:00+03:00"],
                cwd=engineer_root,
                check=True,
                capture_output=True,
                text=True,
            )
            status_dir = architect_root / "docs"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "STATUS.md").write_text(
                "\n".join(
                    [
                        "# STATUS",
                        "- Дата и время: `2026-04-02 13:10 MSK`",
                        "- Что сделано: оформили playbook и убрали ручной контур.",
                    ]
                ),
                encoding="utf-8",
            )
            fake_gh = engineer_root / "gh"
            fake_gh.write_text("#!/usr/bin/env python3\nprint('[]')\n", encoding="utf-8")
            fake_gh.chmod(0o755)
            agent = LarisaIvanovnaAgent(
                config=DEFAULT_CONFIG,
                dependencies=LarisaDependencies(
                    calendar_provider=NullCalendarProvider(),
                    tasks_provider=NullTasksProvider(),
                    weather_provider=NullWeatherProvider(),
                    telegram_provider=NullTelegramProvider(),
                    content_topics_deps=ContentTopicsWorkflowDeps(
                        engineer_root=engineer_root,
                        architect_root=architect_root,
                        tasks_provider=StaticTasksProvider(
                            TaskDaySnapshot(
                                date_msk="02.04.2026",
                                tasks_for_today=(TaskItem(id="1", title="Сверить playbook", bucket="today"),),
                                source_available=True,
                            )
                        ),
                        gh_binary=str(fake_gh),
                    ),
                ),
            )

            result = agent.execute(
                "get_content_post",
                {"date_msk": "02.04.2026", "period_key": "day", "topic_index": 1, "tone": "business"},
            )
            self.assertIn("Режим: business", result["text"])
            self.assertIn("стоимость управления", result["text"])

    def test_day_brief_command_returns_telegram_friendly_sections(self) -> None:
        agent = self._build_agent()

        result = agent.execute(
            "get_day_brief",
            DayBriefRequest(date_msk="22.03.2026", weekday_msk="воскресенье"),
        )

        text = result["text"]
        self.assertIn("🗓️ <b>Календарь дня:</b>", text)
        self.assertIn("⏰ <b>Просроченные задачи:</b>", text)
        self.assertIn("✅ <b>Задачи на сегодня:</b>", text)
        self.assertIn("⚠️ <b>Ограничения:</b>", text)

    def test_brief_with_available_sources_keeps_other_sections(self) -> None:
        agent = self._build_agent(
            calendar_provider=StaticCalendarProvider(
                CalendarDaySnapshot(
                    date_msk="22.03.2026",
                    meetings=(
                        CalendarEvent(
                            id="1",
                            title="Созвон",
                            start_at_msk="2026-03-22T10:00:00+03:00",
                            end_at_msk="2026-03-22T10:30:00+03:00",
                        ),
                    ),
                    source_available=True,
                )
            ),
            tasks_provider=StaticTasksProvider(
                TaskDaySnapshot(
                    date_msk="22.03.2026",
                    tasks_for_today=(TaskItem(id="1", title="Подготовить заметки", bucket="today"),),
                    source_available=True,
                )
            ),
            weather_provider=StaticWeatherProvider(
                WeatherSnapshot(city="Москва", summary="ясно", temperature_text="сейчас 5°C", source_available=True)
            ),
        )

        result = agent.execute("get_day_brief", DayBriefRequest(date_msk="22.03.2026", weekday_msk="воскресенье"))
        self.assertIn("Созвон", result["text"])
        self.assertIn("🗓️ <b>Календарь дня:</b>", result["text"])
        self.assertIn("✅ <b>Задачи на сегодня:</b>", result["text"])
        self.assertIn("Подготовить заметки", result["text"])
        self.assertNotIn("Новости", result["text"])

    def test_brief_renders_meeting_times_in_europe_moscow(self) -> None:
        agent = self._build_agent(
            calendar_provider=StaticCalendarProvider(
                CalendarDaySnapshot(
                    date_msk="25.03.2026",
                    meetings=(
                        CalendarEvent(
                            id="1",
                            title="UTC-встреча",
                            start_at_msk="2026-03-25T05:30:00+00:00",
                            end_at_msk="2026-03-25T06:30:00+00:00",
                        ),
                    ),
                    source_available=True,
                )
            ),
            tasks_provider=StaticTasksProvider(TaskDaySnapshot(date_msk="25.03.2026", source_available=True)),
            weather_provider=StaticWeatherProvider(
                WeatherSnapshot(city="Москва", summary="ясно", temperature_text="сейчас 5°C", source_available=True)
            ),
        )

        result = agent.execute("get_day_brief", DayBriefRequest(date_msk="25.03.2026", weekday_msk="среда"))
        self.assertIn("<b>08:30-09:30</b> UTC-встреча", result["text"])
        self.assertNotIn("05:30-06:30 UTC-встреча", result["text"])

    def test_midday_replan_skips_when_scope_is_balanced(self) -> None:
        agent = self._build_agent(
            tasks_provider=StaticTasksProvider(
                TaskDaySnapshot(
                    date_msk="26.03.2026",
                    tasks_for_today=(
                        TaskItem(id="1", title="Сверить отчёт", bucket="today", priority="4"),
                        TaskItem(id="2", title="Написать Оле", bucket="today", priority="3"),
                    ),
                    source_available=True,
                )
            ),
        )

        result = agent.execute("get_midday_replan", {"date_msk": "26.03.2026", "now_hour_msk": 14})
        self.assertFalse(result["should_send"])
        self.assertIn("midday_skip_balanced", result["text"])

    def test_brief_without_weather_keeps_other_sections(self) -> None:
        agent = self._build_agent(
            calendar_provider=StaticCalendarProvider(
                CalendarDaySnapshot(date_msk="22.03.2026", source_available=True)
            ),
            tasks_provider=StaticTasksProvider(
                TaskDaySnapshot(
                    date_msk="22.03.2026",
                    overdue_tasks=(TaskItem(id="1", title="Просроченный follow-up", bucket="overdue"),),
                    source_available=True,
                )
            ),
            weather_provider=FailingWeatherProvider(),
        )

        result = agent.execute("get_day_brief", DayBriefRequest(date_msk="22.03.2026", weekday_msk="воскресенье"))
        self.assertIn("Просроченный follow-up", result["text"])
        self.assertIn("Погода недоступна", result["text"])
        self.assertIn("⏰ <b>Просроченные задачи:</b>", result["text"])

    def test_open_meteo_weather_provider_retries_transient_error(self) -> None:
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = json.dumps(
            {
                "current_weather": {"temperature": 7, "weathercode": 3},
                "daily": {
                    "temperature_2m_max": [9],
                    "temperature_2m_min": [2],
                    "precipitation_probability_max": [20],
                },
            }
        ).encode("utf-8")
        provider = OpenMeteoWeatherProvider(timeout_sec=1, retry_delays_sec=(0.0, 0.0))

        with patch(
            "apps.larisa_ivanovna.providers.weather_provider.urlopen",
            side_effect=[URLError("EOF occurred in violation of protocol"), response],
        ) as mocked_urlopen:
            weather = provider.get_weather("29.03.2026", "Москва")

        self.assertTrue(weather.source_available)
        self.assertEqual(weather.source, "open-meteo")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_open_meteo_weather_provider_returns_unavailable_after_retries(self) -> None:
        provider = OpenMeteoWeatherProvider(timeout_sec=1, retry_delays_sec=(0.0, 0.0))

        with patch(
            "apps.larisa_ivanovna.providers.weather_provider.urlopen",
            side_effect=URLError("temporary weather outage"),
        ) as mocked_urlopen:
            weather = provider.get_weather("29.03.2026", "Москва")

        self.assertFalse(weather.source_available)
        self.assertIn("Open-Meteo недоступен", weather.limitation or "")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_brief_without_calendar_keeps_other_sections(self) -> None:
        agent = self._build_agent(
            calendar_provider=FailingCalendarProvider(),
            tasks_provider=StaticTasksProvider(
                TaskDaySnapshot(
                    date_msk="22.03.2026",
                    tasks_for_today=(TaskItem(id="1", title="Закрыть задачу", bucket="today"),),
                    source_available=True,
                )
            ),
        )

        result = agent.execute("get_day_brief", DayBriefRequest(date_msk="22.03.2026", weekday_msk="воскресенье"))
        self.assertIn("Закрыть задачу", result["text"])
        self.assertIn("Календарь недоступен", result["text"])
        self.assertIn("✅ <b>Задачи на сегодня:</b>", result["text"])

    def test_bitrix_calendar_provider_reads_events_through_app_state(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    {
                        "saved_at": "2026-03-22T08:00:00+03:00",
                        "payload": {
                            "auth[access_token]": "token",
                            "auth[refresh_token]": "refresh",
                            "auth[client_endpoint]": "https://portal/rest",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = BitrixCalendarProvider(
                env_data={
                    "BITRIX_APP_STATE_DIR": str(state_dir),
                    "BITRIX_CLIENT_ID": "local.app",
                    "BITRIX_CLIENT_SECRET": "secret",
                }
            )

            with patch.object(
                provider.app_auth,
                "call_method",
                side_effect=[
                    {"ID": "42"},
                    [
                        {
                            "ID": "1",
                            "NAME": "Совещание",
                            "DATE_FROM": "2026-03-22T10:00:00+03:00",
                            "DATE_TO": "2026-03-22T10:30:00+03:00",
                        }
                    ],
                ],
            ) as mocked_call:
                snapshot = provider.get_day_snapshot("22.03.2026")

            self.assertTrue(snapshot.source_available)
            self.assertEqual(len(snapshot.meetings), 1)
            self.assertEqual(snapshot.meetings[0].title, "Совещание")
            self.assertEqual(mocked_call.call_args_list[0].args[0], "profile")
            self.assertEqual(mocked_call.call_args_list[1].args[0], "calendar.event.get")

    def test_bitrix_calendar_provider_normalizes_times_to_moscow_day(self) -> None:
        provider = BitrixCalendarProvider(env_data={})
        with patch.object(
            provider,
            "_load_calendar_events",
            return_value=[
                {
                    "ID": "1",
                    "NAME": "Поздняя встреча",
                    "DATE_FROM": "2026-03-24T21:30:00+00:00",
                    "DATE_TO": "2026-03-24T22:30:00+00:00",
                }
            ],
        ):
            snapshot = provider.get_day_snapshot("25.03.2026")

        self.assertTrue(snapshot.source_available)
        self.assertEqual(len(snapshot.meetings), 1)
        self.assertEqual(snapshot.meetings[0].start_at_msk, "2026-03-25T00:30:00+03:00")
        self.assertEqual(snapshot.meetings[0].end_at_msk, "2026-03-25T01:30:00+03:00")

    def test_bitrix_calendar_provider_skips_declined_meetings_and_inactive_participants(self) -> None:
        provider = BitrixCalendarProvider(env_data={"LARISA_BITRIX_USER_ID": "12"})
        with (
            patch.object(
                provider,
                "_load_calendar_events",
                return_value=[
                    {
                        "ID": "1",
                        "NAME": "Лишняя планерка",
                        "DATE_FROM": "2026-04-13T10:00:00+03:00",
                        "DATE_TO": "2026-04-13T11:00:00+03:00",
                        "IS_MEETING": True,
                        "MEETING_STATUS": "N",
                        "ATTENDEES_CODES": ["U12", "U656"],
                    },
                    {
                        "ID": "2",
                        "NAME": "Нужный weekly",
                        "DATE_FROM": "2026-04-13T12:00:00+03:00",
                        "DATE_TO": "2026-04-13T13:00:00+03:00",
                        "IS_MEETING": True,
                        "MEETING_STATUS": "Y",
                        "ATTENDEES_CODES": ["U12", "U656", "U918"],
                    },
                ],
            ),
            patch.object(
                provider.app_auth,
                "call_method",
                side_effect=[
                    [{"ID": "656", "ACTIVE": False, "NAME": "Ксения", "LAST_NAME": "Тильканова"}],
                    [{"ID": "918", "ACTIVE": True, "NAME": "Роман", "LAST_NAME": "Качесов"}],
                ],
            ),
        ):
            snapshot = provider.get_day_snapshot("13.04.2026")

        self.assertTrue(snapshot.source_available)
        self.assertEqual(len(snapshot.meetings), 1)
        self.assertEqual(snapshot.meetings[0].title, "Нужный weekly")
        self.assertEqual(snapshot.meetings[0].participants, ("Роман Качесов",))

    def test_bitrix_calendar_provider_creates_event_through_app_state(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    {
                        "saved_at": "2026-03-22T08:00:00+03:00",
                        "payload": {
                            "auth[access_token]": "token",
                            "auth[refresh_token]": "refresh",
                            "auth[client_endpoint]": "https://portal/rest",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = BitrixCalendarProvider(
                env_data={
                    "BITRIX_APP_STATE_DIR": str(state_dir),
                    "BITRIX_CLIENT_ID": "local.app",
                    "BITRIX_CLIENT_SECRET": "secret",
                }
            )
            payload = CreateCalendarEventInput(
                title="Стратегическая сессия",
                start_at_msk="2026-03-22T14:00:00+03:00",
                end_at_msk="2026-03-22T14:30:00+03:00",
            )

            with patch.object(
                provider.app_auth,
                "call_method",
                side_effect=[
                    {"ID": "42"},
                    {"ID": "99"},
                ],
            ) as mocked_call:
                result = provider.create_event(payload)

            self.assertTrue(result["created"])
            self.assertEqual(result["event"].id, "99")
            self.assertEqual(mocked_call.call_args_list[1].args[0], "calendar.event.add")

    def test_todoist_tasks_provider_normalizes_url_only_titles(self) -> None:
        provider = TodoistTasksProvider(env_data={})
        with patch.object(
            provider,
            "_load_tasks",
            return_value=[
                {
                    "id": "42",
                    "content": "https://belberrycrm.bitrix24.ru/company/personal/user/12/tasks/task/view/365576/",
                    "priority": 4,
                    "due": {"date": "2026-03-26"},
                }
            ],
        ):
            snapshot = provider.get_day_snapshot("26.03.2026")

        self.assertTrue(snapshot.source_available)
        self.assertEqual(snapshot.tasks_for_today[0].title, "CRM задача")

    def test_todoist_tasks_provider_prefers_shared_snapshot_when_fresh(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "tasks_snapshot.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2026-03-26T06:15:00Z",
                        "timezone": "Europe/Moscow",
                        "today": "2026-03-26",
                        "tasks": [
                            {
                                "id": "snap-1",
                                "content": "Из общего snapshot",
                                "dueDate": "2026-03-26",
                                "dueDateTime": None,
                                "completed": False,
                                "priority": 4,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = TodoistTasksProvider(
                env_data={
                    "TODO_STATE_DIR": str(state_dir),
                    "LARISA_TODO_SNAPSHOT_MAX_AGE_MIN": "0",
                    "LARISA_TODO_TOKEN": "token",
                }
            )

            with patch.object(provider, "_load_tasks_from_api", side_effect=AssertionError("API не должен вызываться")):
                snapshot = provider.get_day_snapshot("26.03.2026")

        self.assertTrue(snapshot.source_available)
        self.assertEqual(snapshot.tasks_for_today[0].title, "Из общего snapshot")

    def test_todoist_tasks_provider_uses_api_when_snapshot_stale(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "tasks_snapshot.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2025-03-26T06:15:00Z",
                        "timezone": "Europe/Moscow",
                        "today": "2025-03-26",
                        "tasks": [
                            {
                                "id": "snap-1",
                                "content": "Старый snapshot",
                                "dueDate": "2026-03-26",
                                "dueDateTime": None,
                                "completed": False,
                                "priority": 1,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = TodoistTasksProvider(
                env_data={
                    "TODO_STATE_DIR": str(state_dir),
                    "LARISA_TODO_SNAPSHOT_MAX_AGE_MIN": "1",
                    "LARISA_TODO_TOKEN": "token",
                }
            )

            with patch.object(
                provider,
                "_load_tasks_from_api",
                return_value=[
                    {
                        "id": "api-1",
                        "content": "Актуальная задача из API",
                        "priority": 4,
                        "due": {"date": "2026-03-26"},
                    }
                ],
            ):
                snapshot = provider.get_day_snapshot("26.03.2026")

        self.assertTrue(snapshot.source_available)
        self.assertEqual(snapshot.tasks_for_today[0].title, "Актуальная задача из API")

    def test_todoist_tasks_provider_falls_back_to_snapshot_when_api_is_unavailable(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "tasks_snapshot.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2025-03-26T06:15:00Z",
                        "timezone": "Europe/Moscow",
                        "today": "2025-03-26",
                        "tasks": [
                            {
                                "id": "snap-1",
                                "content": "Snapshot без потери данных",
                                "dueDate": "2026-03-26",
                                "dueDateTime": None,
                                "completed": False,
                                "priority": 3,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = TodoistTasksProvider(
                env_data={
                    "TODO_STATE_DIR": str(state_dir),
                    "LARISA_TODO_SNAPSHOT_MAX_AGE_MIN": "1",
                    "LARISA_TODO_TOKEN": "token",
                }
            )

            with patch.object(
                provider,
                "_load_tasks_from_api",
                side_effect=RuntimeError("HTTP Error 502: Bad Gateway"),
            ):
                snapshot = provider.get_day_snapshot("26.03.2026")

        self.assertTrue(snapshot.source_available)
        self.assertIsNone(snapshot.limitation)
        self.assertEqual(snapshot.tasks_for_today[0].title, "Snapshot без потери данных")


class LarisaWorkflowRoutingTests(unittest.TestCase):
    def test_router_maps_larisa_commands(self) -> None:
        self.assertEqual(select_workflow({"command": "/brief"}), "day_briefing")
        self.assertEqual(select_workflow({"command": "/weather"}), "larisa_weather")
        self.assertEqual(select_workflow({"command": "/search"}), "larisa_search")
        self.assertEqual(select_workflow({"command": "/plan-day"}), "larisa_plan_day")
        self.assertEqual(select_workflow({"command": "/topics"}), "larisa_content_topics")
        self.assertEqual(select_workflow({"command": "/draft"}), "larisa_content_post")
        self.assertEqual(select_workflow({"command": "/business"}), "larisa_content_post")
        self.assertEqual(select_workflow({"command": "/tasks"}), "tasks_summary")

    def test_removed_surfaces_are_not_exposed(self) -> None:
        for command in ("/news", "/add-meeting", "/create-event"):
            self.assertIsNone(extract_command(command))
            self.assertNotIn(command, COMMAND_ROUTES)

    def test_free_text_question_routes_to_search(self) -> None:
        self.assertEqual(
            select_workflow({"text": "как сегодня сыграл ЦСКА?", "chat_id": "42", "user_id": "99"}),
            "larisa_search",
        )

    def test_day_briefing_workflow_delegates_to_larisa_agent(self) -> None:
        fake_agent = Mock()
        fake_agent.execute.return_value = {"text": "brief ok", "payload": {"kind": "brief"}}

        with patch("cloudbot.workflows.larisa_runtime.build_larisa_agent_from_env", return_value=fake_agent):
            result = day_briefing.run({"message": {"text": "/today", "command": "/today"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow"], "day_briefing")
        self.assertEqual(result["agent_id"], "larisa_ivanovna")
        self.assertEqual(result["text"], "brief ok")
        fake_agent.execute.assert_called_once()

    def test_build_day_brief_request_uses_moscow_calendar_day(self) -> None:
        request = day_briefing.build_day_brief_request(datetime(2026, 3, 24, 21, 30, tzinfo=timezone.utc))
        self.assertEqual(request.date_msk, "25.03.2026")
        self.assertEqual(request.weekday_msk, "среда")

    def test_route_bridge_uses_larisa_route_alias(self) -> None:
        provider = SharedTelegramRouteProvider(
            env_data={
                "TELEGRAM_TARGETS": "larisa-ivanovna=700700",
                "TELEGRAM_ALLOWED_CHAT_IDS": "700700",
                "TELEGRAM_DRY_RUN": "1",
            }
        )

        description = provider.describe_route()
        delivery = provider.send("test")

        self.assertEqual(description.route_key, "larisa-ivanovna")
        self.assertEqual(delivery["route_key"], "larisa-ivanovna")
        self.assertEqual(delivery["chat_id"], "700700")
        self.assertTrue(delivery["dry_run"])


if __name__ == "__main__":
    unittest.main()
