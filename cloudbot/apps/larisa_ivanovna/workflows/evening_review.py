"""Вечерний обзор для Ларисы Ивановны."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from ..providers.tasks_provider import TasksProvider
from ..schemas.task import TaskDaySnapshot, TaskItem


@dataclass(frozen=True)
class EveningReviewWorkflowDeps:
    tasks_provider: TasksProvider


def run_evening_review_workflow(
    *,
    date_msk: str,
    deps: EveningReviewWorkflowDeps,
) -> dict[str, object]:
    try:
        snapshot = deps.tasks_provider.get_day_snapshot(date_msk)
    except Exception as error:  # noqa: BLE001
        snapshot = TaskDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation=f"Задачи недоступны: {error}",
        )

    if not snapshot.source_available:
        return {
            "text": snapshot.limitation or "Источник задач недоступен.",
            "snapshot": snapshot,
            "should_send": True,
        }

    overdue = _sort_tasks(snapshot.overdue_tasks)
    due_today = _sort_tasks(snapshot.tasks_for_today)
    merged = _dedupe_tasks((*overdue, *due_today))
    collapsed = _collapse_tasks(merged)
    carry_to_tomorrow = _pick_carry_to_tomorrow(collapsed)
    overdue_visible = tuple(
        entry
        for entry in collapsed
        if entry.task.bucket == "overdue"
        and not _is_ambiguous_title(entry.task.title)
        and entry.key not in {item.key for item in carry_to_tomorrow}
    )[:6]
    due_today_visible = tuple(
        entry
        for entry in collapsed
        if entry.task.bucket == "today"
        and entry.key not in {item.key for item in carry_to_tomorrow}
    )[:5]
    ambiguous = tuple(entry for entry in collapsed if _is_ambiguous_title(entry.task.title))[:5]

    lines = [
        "🌙 Вечерний чек",
        "",
        f"{date_msk} • просрочено {len(overdue)} • осталось на сегодня {len(due_today)}",
    ]

    if carry_to_tomorrow:
        lines.extend(["", "Что вынести на завтра"])
        lines.extend(_format_review_entry(entry, date_msk) for entry in carry_to_tomorrow)

    if due_today_visible:
        lines.extend(["", "Не закрыто сегодня"])
        lines.extend(_format_review_entry(entry, date_msk) for entry in due_today_visible)

    if overdue_visible:
        lines.extend(["", "Самое просроченное"])
        lines.extend(_format_review_entry(entry, date_msk) for entry in overdue_visible)

    if ambiguous:
        lines.extend(["", "Нужно уточнить названия"])
        lines.extend(_format_review_entry(entry, date_msk, show_due=False) for entry in ambiguous)

    if not collapsed:
        lines.extend(["", "Открытых задач на конец дня не осталось."])

    return {
        "text": "\n".join(lines),
        "snapshot": snapshot,
        "should_send": True,
    }


@dataclass(frozen=True)
class ReviewEntry:
    key: str
    task: TaskItem
    count: int = 1


def _dedupe_tasks(tasks: tuple[TaskItem, ...]) -> tuple[TaskItem, ...]:
    seen: set[str] = set()
    out: list[TaskItem] = []
    for task in tasks:
        key = f"{task.id}:{task.title}:{task.bucket}"
        if key in seen:
            continue
        seen.add(key)
        out.append(task)
    return tuple(out)


def _sort_tasks(tasks: tuple[TaskItem, ...]) -> tuple[TaskItem, ...]:
    return tuple(
        sorted(
            tasks,
            key=lambda item: (
                _priority_bucket(item.priority),
                _due_sort_key(item.due_at_msk),
                item.title.lower(),
            ),
        )
    )


def _collapse_tasks(tasks: tuple[TaskItem, ...]) -> tuple[ReviewEntry, ...]:
    groups: dict[str, list[TaskItem]] = {}
    for task in tasks:
        key = _normalize_title(task.title)
        groups.setdefault(key, []).append(task)

    entries: list[ReviewEntry] = []
    for key, group in groups.items():
        representative = sorted(
            group,
            key=lambda item: (
                0 if item.bucket == "today" else 1,
                _priority_bucket(item.priority),
                _due_sort_key(item.due_at_msk),
                item.title.lower(),
            ),
        )[0]
        entries.append(ReviewEntry(key=key, task=representative, count=len(group)))

    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                _carry_rank(entry),
                _priority_bucket(entry.task.priority),
                _due_sort_key(entry.task.due_at_msk),
                entry.task.title.lower(),
            ),
        )
    )


def _pick_carry_to_tomorrow(entries: tuple[ReviewEntry, ...]) -> tuple[ReviewEntry, ...]:
    concrete = [entry for entry in entries if not _is_ambiguous_title(entry.task.title)]
    picked = concrete[:3]
    if len(picked) >= 3:
        return tuple(picked)

    extra = [entry for entry in entries if entry.key not in {item.key for item in picked}]
    return tuple((*picked, *extra[: 3 - len(picked)]))


def _format_review_entry(entry: ReviewEntry, date_msk: str, *, show_due: bool = True) -> str:
    due_label = _format_due_label(entry.task.due_at_msk, date_msk) if show_due else ""
    count_label = f" ×{entry.count}" if entry.count > 1 else ""
    if due_label:
        return f"- {due_label} • {entry.task.title}{count_label}"
    return f"- {entry.task.title}{count_label}"


def _format_due_label(raw_due: str, date_msk: str) -> str:
    due_value = _parse_due_value(raw_due)
    if due_value is None:
        return ""

    report_date = datetime.strptime(date_msk, "%d.%m.%Y").date()
    if isinstance(due_value, datetime):
        if due_value.date() == report_date:
            return due_value.strftime("%H:%M")
        return due_value.strftime("%d.%m %H:%M")
    return due_value.strftime("%d.%m")


def _parse_due_value(raw_due: str) -> date | datetime | None:
    prepared = str(raw_due or "").strip()
    if not prepared:
        return None
    try:
        if "T" in prepared:
            return datetime.fromisoformat(prepared.replace("Z", "+00:00"))
        return datetime.strptime(prepared[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _due_sort_key(raw_due: str) -> tuple[int, str]:
    due_value = _parse_due_value(raw_due)
    if due_value is None:
        return (1, "9999-12-31T23:59")
    if isinstance(due_value, datetime):
        return (0, due_value.isoformat(timespec="minutes"))
    return (0, due_value.isoformat())


def _normalize_title(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def _is_ambiguous_title(title: str) -> bool:
    normalized = _normalize_title(title)
    return normalized in {
        "google sheet",
        "crm задача",
        "ссылка",
        "задача",
        "sheet",
    }


def _carry_rank(entry: ReviewEntry) -> tuple[int, int]:
    return (
        0 if entry.task.bucket == "today" else 1,
        1 if _is_ambiguous_title(entry.task.title) else 0,
    )


def _priority_bucket(raw_priority: str) -> int:
    prepared = str(raw_priority or "").strip().lower()
    if prepared.isdigit():
        return max(1, 5 - int(prepared))
    if prepared in {"p1", "high", "highest"}:
        return 1
    if prepared in {"p2", "medium"}:
        return 2
    if prepared in {"p3", "low"}:
        return 3
    return 4
