"""Сборка daily brief Ларисы Ивановны."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_CONFIG
from ..providers.calendar_provider import CalendarProvider
from ..providers.tasks_provider import TasksProvider
from ..providers.weather_provider import WeatherProvider
from ..schemas.brief import DayBrief, DayBriefRequest, FocusBlock, FreeWindow, WeatherSnapshot
from ..schemas.calendar import CalendarDaySnapshot, CalendarEvent
from ..schemas.task import TaskDaySnapshot, TaskItem
from ..timezone import extract_moscow_clock


@dataclass(frozen=True)
class DailyBriefWorkflowDeps:
    calendar_provider: CalendarProvider
    tasks_provider: TasksProvider
    weather_provider: WeatherProvider


def build_day_brief(
    request: DayBriefRequest,
    deps: DailyBriefWorkflowDeps,
) -> DayBrief:
    calendar_snapshot = _load_calendar_snapshot(request, deps)
    task_snapshot = _load_task_snapshot(request, deps)
    weather_snapshot = _load_weather_snapshot(request, deps)

    free_windows = (
        _calculate_free_windows(calendar_snapshot.meetings)
        if calendar_snapshot.source_available
        else tuple()
    )
    focus_blocks = _build_focus_blocks(
        tasks_for_today=task_snapshot.tasks_for_today,
        overdue_tasks=task_snapshot.overdue_tasks,
        free_windows=free_windows,
    )
    limitations = tuple(
        item
        for item in (
            calendar_snapshot.limitation,
            task_snapshot.limitation,
            weather_snapshot.limitation,
        )
        if item
    )

    return DayBrief(
        date_msk=request.date_msk,
        weekday_msk=request.weekday_msk,
        timezone=DEFAULT_CONFIG.timezone,
        meetings=calendar_snapshot.meetings,
        tasks_for_today=task_snapshot.tasks_for_today,
        overdue_tasks=task_snapshot.overdue_tasks,
        free_windows=free_windows,
        focus_blocks=focus_blocks,
        weather=weather_snapshot,
        focus=_build_focus(
            meetings=calendar_snapshot.meetings,
            tasks_for_today=task_snapshot.tasks_for_today,
            overdue_tasks=task_snapshot.overdue_tasks,
            free_windows=free_windows,
            focus_blocks=focus_blocks,
        ),
        action_items=_build_action_items(
            meetings=calendar_snapshot.meetings,
            tasks_for_today=task_snapshot.tasks_for_today,
            overdue_tasks=task_snapshot.overdue_tasks,
            free_windows=free_windows,
            focus_blocks=focus_blocks,
        ),
        limitations=limitations,
    )


def _load_calendar_snapshot(
    request: DayBriefRequest,
    deps: DailyBriefWorkflowDeps,
) -> CalendarDaySnapshot:
    try:
        return deps.calendar_provider.get_day_snapshot(request.date_msk)
    except Exception as error:  # noqa: BLE001
        return CalendarDaySnapshot(
            date_msk=request.date_msk,
            source_available=False,
            limitation=f"Календарь недоступен: {error}",
        )


def _load_task_snapshot(
    request: DayBriefRequest,
    deps: DailyBriefWorkflowDeps,
) -> TaskDaySnapshot:
    try:
        return deps.tasks_provider.get_day_snapshot(request.date_msk)
    except Exception as error:  # noqa: BLE001
        return TaskDaySnapshot(
            date_msk=request.date_msk,
            source_available=False,
            limitation=f"Задачи недоступны: {error}",
        )


def _load_weather_snapshot(
    request: DayBriefRequest,
    deps: DailyBriefWorkflowDeps,
) -> WeatherSnapshot:
    try:
        return deps.weather_provider.get_weather(request.date_msk, DEFAULT_CONFIG.default_city)
    except Exception as error:  # noqa: BLE001
        return WeatherSnapshot(
            city=DEFAULT_CONFIG.default_city,
            summary="Не удалось загрузить погоду.",
            source_available=False,
            limitation=f"Погода недоступна: {error}",
        )

def _calculate_free_windows(
    meetings: tuple[CalendarEvent, ...],
    *,
    day_start: str = "08:00",
    day_end: str = "19:00",
) -> tuple[FreeWindow, ...]:
    if not meetings:
        return (
            FreeWindow(
                start_at_msk=day_start,
                end_at_msk=day_end,
            ),
        )

    sorted_meetings = tuple(
        sorted(meetings, key=lambda item: _to_minutes(_extract_clock(item.start_at_msk)))
    )
    windows: list[FreeWindow] = []
    cursor = _to_minutes(day_start)
    day_end_minutes = _to_minutes(day_end)

    for meeting in sorted_meetings:
        meeting_start = _to_minutes(_extract_clock(meeting.start_at_msk))
        meeting_end = _to_minutes(_extract_clock(meeting.end_at_msk))
        if meeting_start > cursor:
            windows.append(FreeWindow(start_at_msk=_from_minutes(cursor), end_at_msk=_from_minutes(meeting_start)))
        if meeting_end > cursor:
            cursor = meeting_end

    if cursor < day_end_minutes:
        windows.append(FreeWindow(start_at_msk=_from_minutes(cursor), end_at_msk=_from_minutes(day_end_minutes)))

    return tuple(windows)


def _build_focus(
    *,
    meetings: tuple[CalendarEvent, ...],
    tasks_for_today: tuple[object, ...],
    overdue_tasks: tuple[object, ...],
    free_windows: tuple[FreeWindow, ...],
    focus_blocks: tuple[FocusBlock, ...],
) -> str:
    if focus_blocks:
        first = focus_blocks[0]
        return f"Фокус-блок {first.start_at_msk}-{first.end_at_msk}: {first.title}."
    if not meetings and not tasks_for_today and not overdue_tasks:
        return "Подтвержденных событий мало. День нужно собрать вокруг личных приоритетов."
    if overdue_tasks:
        return f"Сначала закрыть просроченное: {getattr(overdue_tasks[0], 'title', 'без названия')}."
    if meetings:
        return f"День привязан к встрече {_extract_clock(meetings[0].start_at_msk)}: {meetings[0].title}."
    if free_windows:
        return f"Есть окно {free_windows[0].start_at_msk}-{free_windows[0].end_at_msk} для фокусной работы."
    return f"Главный приоритет дня: {getattr(tasks_for_today[0], 'title', 'без названия')}."


def _build_action_items(
    *,
    meetings: tuple[CalendarEvent, ...],
    tasks_for_today: tuple[object, ...],
    overdue_tasks: tuple[object, ...],
    free_windows: tuple[FreeWindow, ...],
    focus_blocks: tuple[FocusBlock, ...],
) -> tuple[str, ...]:
    items: list[str] = []
    if overdue_tasks:
        items.append(f"Закрыть просроченную задачу: {getattr(overdue_tasks[0], 'title', 'без названия')}.")
    if tasks_for_today:
        items.append(f"Зафиксировать время на задачу: {getattr(tasks_for_today[0], 'title', 'без названия')}.")
    if focus_blocks:
        first = focus_blocks[0]
        items.append(f"Забронировать фокус-блок {first.start_at_msk}-{first.end_at_msk}: {first.title}.")
    if meetings:
        items.append(f"Подготовиться к встрече {_extract_clock(meetings[0].start_at_msk)}: {meetings[0].title}.")
    elif free_windows:
        items.append(
            f"Использовать окно {free_windows[0].start_at_msk}-{free_windows[0].end_at_msk} для фокусной работы."
        )
    if not items:
        items.append("Уточнить календарь и задачи перед началом дня.")
    return tuple(items[:3])


def _extract_clock(value: str) -> str:
    return extract_moscow_clock(value)


def _to_minutes(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)


def _from_minutes(value: int) -> str:
    hours = str(value // 60).zfill(2)
    minutes = str(value % 60).zfill(2)
    return f"{hours}:{minutes}"


def _build_focus_blocks(
    *,
    tasks_for_today: tuple[TaskItem, ...],
    overdue_tasks: tuple[TaskItem, ...],
    free_windows: tuple[FreeWindow, ...],
) -> tuple[FocusBlock, ...]:
    candidates = [
        task
        for task in (*overdue_tasks, *tasks_for_today)
        if not _task_has_fixed_time(task)
    ]
    if not candidates or not free_windows:
        return tuple()

    sorted_candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (
                0 if item.bucket == "overdue" else 1,
                _priority_rank(item.priority),
                item.title.lower(),
            ),
        )
    )

    preferred_windows = tuple(
        (_to_minutes(raw.split("-", maxsplit=1)[0]), _to_minutes(raw.split("-", maxsplit=1)[1]))
        for raw in DEFAULT_CONFIG.focus_preferred_windows
    )

    blocks: list[FocusBlock] = []
    for task in sorted_candidates:
        overlap = _pick_focus_overlap(
            free_windows=free_windows,
            preferred_windows=preferred_windows,
            used_blocks=blocks,
        )
        if overlap is None:
            break
        start_min, end_min = overlap
        blocks.append(
            FocusBlock(
                start_at_msk=_from_minutes(start_min),
                end_at_msk=_from_minutes(end_min),
                title=task.title,
            )
        )
        if len(blocks) >= 2:
            break

    return tuple(blocks)


def _pick_focus_overlap(
    *,
    free_windows: tuple[FreeWindow, ...],
    preferred_windows: tuple[tuple[int, int], ...],
    used_blocks: list[FocusBlock],
) -> tuple[int, int] | None:
    used_ranges = {
        (_to_minutes(item.start_at_msk), _to_minutes(item.end_at_msk))
        for item in used_blocks
    }
    for preferred_start, preferred_end in preferred_windows:
        for window in free_windows:
            window_start = _to_minutes(window.start_at_msk)
            window_end = _to_minutes(window.end_at_msk)
            start_min = max(window_start, preferred_start)
            end_min = min(window_end, preferred_end)
            if end_min - start_min < 45:
                continue
            candidate = (start_min, end_min)
            if candidate in used_ranges:
                continue
            return candidate
    return None


def _task_has_fixed_time(task: TaskItem) -> bool:
    return "T" in str(task.due_at_msk or "")


def _priority_rank(raw_priority: str) -> int:
    prepared = str(raw_priority or "").strip().lower()
    if prepared.isdigit():
        return -int(prepared)
    if prepared in {"p1", "high", "highest"}:
        return -4
    if prepared in {"p2", "medium"}:
        return -3
    if prepared in {"p3", "low"}:
        return -2
    return -1
