"""Skill: создать задачу в Tasks/.

Референсный шаблон. Целевой путь в runtime:
``cloudbot/skills/obsidian_create_task.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .obsidian_provider import ObsidianProvider

TASKS_INDEX = "Tasks/_index.md"


@dataclass(frozen=True)
class CreateTaskResult:
    relative_path: str
    title: str
    due: datetime | None
    created_at: datetime


def create_task(
    provider: ObsidianProvider,
    title: str,
    *,
    due: datetime | None = None,
    notes: str | None = None,
) -> CreateTaskResult:
    """Создать задачу: запись добавляется в `Tasks/_index.md` и
    в отдельный файл `Tasks/YYYY-MM-DD-HHMM-<slug>.md`.
    """

    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValueError("Пустая задача")

    provider.ensure_vault()
    provider.sync_pull()

    moment = provider.now_local()
    slug_source = cleaned_title.lower().replace(" ", "-")
    slug = "".join(ch for ch in slug_source if ch.isalnum() or ch in "-_")[:60] or "task"
    relative_path = f"Tasks/{moment.strftime('%Y-%m-%d-%H%M')}-{slug}.md"

    body_lines = [
        f"# {cleaned_title}",
        "",
        f"- статус: open",
        f"- создано: {moment.isoformat()}",
    ]
    if due is not None:
        body_lines.append(f"- срок: {due.isoformat()}")
    if notes:
        body_lines.extend(["", notes.strip()])

    provider.write_note(relative_path, "\n".join(body_lines))

    due_part = f" (до {due.strftime('%Y-%m-%d %H:%M')})" if due else ""
    index_line = f"- [ ] [[{relative_path}|{cleaned_title}]]{due_part}"
    provider.append_note(TASKS_INDEX, index_line)

    provider.sync_push(f"obsidian: новая задача {relative_path}")

    return CreateTaskResult(
        relative_path=relative_path,
        title=cleaned_title,
        due=due,
        created_at=moment,
    )
