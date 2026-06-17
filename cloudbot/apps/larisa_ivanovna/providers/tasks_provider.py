"""Task-адаптеры Ларисы Ивановны."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ..schemas.task import TaskDaySnapshot, TaskItem

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
TODOIST_ENDPOINT = "https://api.todoist.com/api/v1/tasks"
DEFAULT_TODO_SNAPSHOT_MAX_AGE_MIN = 180
DEFAULT_TODO_SNAPSHOT_DIRS = (
    "/home/node/.openclaw/todo-integration-data",
    "/root/.openclaw/todo-integration-data",
    "/root/.openclaw/workspace/todo-integration/data",
    "/opt/openclaw/state/todo",
)


class TasksProvider(ABC):
    @abstractmethod
    def get_day_snapshot(self, date_msk: str) -> TaskDaySnapshot:
        raise NotImplementedError


class NullTasksProvider(TasksProvider):
    def get_day_snapshot(self, date_msk: str) -> TaskDaySnapshot:
        return TaskDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation="Task provider еще не подключен к контуру Ларисы Ивановны.",
        )


class TodoistTasksProvider(TasksProvider):
    def __init__(self, env_data: Mapping[str, str] | None = None, *, timeout_sec: int = 20) -> None:
        if env_data is None:
            self.env_data = dict(os.environ)
        else:
            self.env_data = {str(key): str(value) for key, value in env_data.items()}
        self.timeout_sec = int(timeout_sec)

    def get_day_snapshot(self, date_msk: str) -> TaskDaySnapshot:
        try:
            raw_tasks = self._load_tasks()
        except Exception as error:  # noqa: BLE001
            return TaskDaySnapshot(
                date_msk=date_msk,
                source_available=False,
                limitation=f"Todo provider недоступен: {error}",
            )

        if raw_tasks is None:
            return TaskDaySnapshot(
                date_msk=date_msk,
                source_available=False,
                limitation="TODO_TOKEN или fixture для задач не заданы.",
            )

        due_date_iso = _to_iso_date(date_msk)
        tasks_for_today: list[TaskItem] = []
        overdue_tasks: list[TaskItem] = []
        for raw_task in raw_tasks:
            normalized = _normalize_task(raw_task)
            if normalized is None:
                continue
            task_date = normalized["due_date"]
            if not task_date:
                continue
            task_item = TaskItem(
                id=normalized["id"],
                title=normalized["title"],
                bucket="today" if task_date == due_date_iso else "overdue",
                priority=normalized["priority"],
                due_at_msk=normalized["due_at_msk"],
                notes=normalized["notes"],
                source=normalized["source"],
            )
            if task_date < due_date_iso:
                overdue_tasks.append(task_item)
            elif task_date == due_date_iso:
                tasks_for_today.append(task_item)

        return TaskDaySnapshot(
            date_msk=date_msk,
            tasks_for_today=tuple(tasks_for_today),
            overdue_tasks=tuple(overdue_tasks),
            source_available=True,
        )

    def _fixture_file(self) -> Path | None:
        candidates = (
            self.env_data.get("LARISA_TODO_FIXTURES_FILE"),
            self.env_data.get("TODO_FIXTURES_FILE"),
            self.env_data.get("TODO_TASKS_FIXTURES_FILE"),
        )
        for candidate in candidates:
            raw = str(candidate or "").strip()
            if raw:
                path = Path(raw).expanduser()
                if path.exists():
                    return path
        return None

    def _load_tasks(self) -> list[dict[str, Any]] | None:
        fixture_file = self._fixture_file()
        if fixture_file is not None:
            payload = json.loads(fixture_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                data = payload.get("tasks") or []
            else:
                data = payload
            return [item for item in data if isinstance(item, dict)]

        shared_snapshot_tasks = self._load_tasks_from_shared_snapshot(allow_stale=False)
        if shared_snapshot_tasks is not None:
            return shared_snapshot_tasks

        api_error: Exception | None = None
        try:
            api_tasks = self._load_tasks_from_api()
        except Exception as error:  # noqa: BLE001
            api_error = error
        else:
            if api_tasks is not None:
                return api_tasks

        shared_snapshot_tasks = self._load_tasks_from_shared_snapshot(allow_stale=True)
        if shared_snapshot_tasks is not None:
            return shared_snapshot_tasks

        if api_error is not None:
            raise api_error
        return None

    def _load_tasks_from_shared_snapshot(self, *, allow_stale: bool) -> list[dict[str, Any]] | None:
        stale_tasks: list[dict[str, Any]] | None = None
        for snapshot_file in self._shared_snapshot_candidates():
            if not snapshot_file.exists():
                continue
            payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
            tasks = payload.get("tasks") if isinstance(payload, dict) else None
            if not isinstance(tasks, list):
                raise ValueError(f"Shared tasks snapshot invalid: {snapshot_file}")
            normalized_tasks = [item for item in tasks if isinstance(item, dict)]
            if self._snapshot_is_stale(payload):
                if stale_tasks is None:
                    stale_tasks = normalized_tasks
                continue
            return normalized_tasks
        return stale_tasks if allow_stale else None

    def _shared_snapshot_candidates(self) -> tuple[Path, ...]:
        seen: set[str] = set()
        candidates: list[Path] = []
        raw_candidates = (
            self.env_data.get("LARISA_TODO_SNAPSHOT_FILE"),
            self.env_data.get("TODO_TASKS_SNAPSHOT_FILE"),
            self.env_data.get("LARISA_TODO_STATE_DIR"),
            self.env_data.get("TODO_STATE_DIR"),
            *DEFAULT_TODO_SNAPSHOT_DIRS,
        )
        for candidate in raw_candidates:
            raw = str(candidate or "").strip()
            if not raw:
                continue
            base_path = Path(raw).expanduser()
            snapshot_file = base_path if base_path.name == "tasks_snapshot.json" else base_path / "tasks_snapshot.json"
            snapshot_key = str(snapshot_file)
            if snapshot_key in seen:
                continue
            seen.add(snapshot_key)
            candidates.append(snapshot_file)
        return tuple(candidates)

    def _snapshot_is_stale(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        max_age_minutes = self._snapshot_max_age_minutes()
        if max_age_minutes <= 0:
            return False
        generated_at_raw = str(payload.get("generatedAt") or "").strip()
        if not generated_at_raw:
            return False
        try:
            generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00")).astimezone(MOSCOW_TZ)
        except ValueError:
            return False
        age_seconds = (datetime.now(MOSCOW_TZ) - generated_at).total_seconds()
        return age_seconds > max_age_minutes * 60

    def _snapshot_max_age_minutes(self) -> int:
        raw_value = str(
            self.env_data.get("LARISA_TODO_SNAPSHOT_MAX_AGE_MIN")
            or self.env_data.get("TODO_SNAPSHOT_MAX_AGE_MIN")
            or DEFAULT_TODO_SNAPSHOT_MAX_AGE_MIN
        ).strip()
        try:
            return max(int(raw_value), 0)
        except ValueError:
            return DEFAULT_TODO_SNAPSHOT_MAX_AGE_MIN

    def _load_tasks_from_api(self) -> list[dict[str, Any]] | None:
        token = str(self.env_data.get("TODO_TOKEN") or self.env_data.get("LARISA_TODO_TOKEN") or "").strip()
        if not token:
            return None

        tasks: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params = {"limit": "100"}
            if cursor:
                params["cursor"] = cursor
            query = "&".join(f"{key}={value}" for key, value in params.items())
            request = Request(
                f"{TODOIST_ENDPOINT}?{query}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            items = payload.get("results") or []
            tasks.extend(item for item in items if isinstance(item, dict))
            cursor = str(payload.get("next_cursor") or "").strip()
            if not cursor or not items:
                break
        return tasks


def _to_iso_date(date_msk: str) -> str:
    return datetime.strptime(date_msk, "%d.%m.%Y").date().isoformat()


def _normalize_task(task: dict[str, Any]) -> dict[str, str] | None:
    if task.get("checked") or task.get("completed") or task.get("completed_at"):
        return None

    due = task.get("due") or {}
    due_date = str(due.get("date") or task.get("dueDate") or task.get("DEADLINE") or "").strip()
    due_datetime = str(due.get("datetime") or task.get("dueDateTime") or "").strip()

    normalized_due_date = ""
    normalized_due_at = ""
    if due_datetime:
        try:
            parsed = datetime.fromisoformat(due_datetime.replace("Z", "+00:00")).astimezone(MOSCOW_TZ)
            normalized_due_date = parsed.date().isoformat()
            normalized_due_at = parsed.isoformat(timespec="minutes")
        except ValueError:
            normalized_due_at = due_datetime
    elif due_date:
        try:
            normalized_due_date = datetime.fromisoformat(due_date[:10]).date().isoformat()
            normalized_due_at = normalized_due_date
        except ValueError:
            try:
                parsed = datetime.fromisoformat(due_date.replace("Z", "+00:00")).astimezone(MOSCOW_TZ)
                normalized_due_date = parsed.date().isoformat()
                normalized_due_at = parsed.isoformat(timespec="minutes")
            except ValueError:
                normalized_due_at = due_date

    if not normalized_due_date and normalized_due_at:
        try:
            normalized_due_date = datetime.fromisoformat(normalized_due_at).date().isoformat()
        except ValueError:
            normalized_due_date = ""

    raw_title = str(task.get("content") or task.get("TITLE") or "").strip()
    title = _normalize_task_title(raw_title, str(task.get("url") or "").strip())
    return {
        "id": str(task.get("id") or task.get("ID") or "").strip(),
        "title": title,
        "priority": str(task.get("priority") or "medium"),
        "due_date": normalized_due_date,
        "due_at_msk": normalized_due_at,
        "notes": str(task.get("description") or task.get("DESCRIPTION") or "").strip(),
        "source": "todoist" if task.get("content") else "todo",
    }


def _normalize_task_title(raw_title: str, fallback_url: str) -> str:
    stripped_title = _strip_links(raw_title)
    if stripped_title:
        return stripped_title
    url = _extract_url(raw_title) or fallback_url
    if url:
        return _normalize_url_title(url)
    return "(без названия)"


def _strip_links(content: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+|\[[^\]]+\]\((https?://[^\s)]+)\)", " ", str(content))).strip()


def _extract_url(content: str) -> str:
    markdown_match = re.search(r"\[[^\]]+\]\((https?://[^\s)]+)\)", str(content))
    if markdown_match:
        return markdown_match.group(1)
    raw_match = re.search(r"https?://\S+", str(content))
    if raw_match:
        return raw_match.group(0)
    return ""


def _normalize_url_title(url: str) -> str:
    prepared = str(url).strip().lower()
    if "bitrix24" in prepared:
        return "CRM задача"
    if "docs.google.com" in prepared and "spreadsheets" in prepared:
        return "Google Sheet"
    if "docs.google.com" in prepared:
        return "Документ"
    return "Ссылка"
