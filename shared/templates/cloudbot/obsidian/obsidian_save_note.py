"""Skill: сохранить произвольную заметку в Inbox.

Референсный шаблон. Целевой путь в runtime:
``cloudbot/skills/obsidian_save_note.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .obsidian_provider import ObsidianProvider

MAX_TITLE_LEN = 60
SLUG_RE = re.compile(r"[^\w\-]+", re.UNICODE)


@dataclass(frozen=True)
class SaveNoteResult:
    relative_path: str
    title: str
    created_at: datetime


def save_note(provider: ObsidianProvider, raw_text: str, *, title: str | None = None) -> SaveNoteResult:
    """Создать заметку в `Inbox/` и закоммитить в git.

    Текст пользователя сохраняется как тело заметки. Заголовок выбирается
    либо из явного параметра, либо из первой строки текста.
    """

    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Пустая заметка")

    provider.ensure_vault()
    provider.sync_pull()

    moment = provider.now_local()
    final_title = (title or _title_from_text(text)).strip() or "Заметка"
    relative_path = f"{provider.config.default_inbox}/{moment.strftime('%Y-%m-%d-%H%M')}-{_slugify(final_title)}.md"

    body = _format_body(final_title, text, moment)
    provider.write_note(relative_path, body)
    provider.sync_push(f"obsidian: новая заметка {relative_path}")

    return SaveNoteResult(relative_path=relative_path, title=final_title, created_at=moment)


def _title_from_text(text: str) -> str:
    first_line = text.splitlines()[0].strip()
    return first_line[:MAX_TITLE_LEN]


def _slugify(title: str) -> str:
    slug = title.lower().replace(" ", "-")
    slug = SLUG_RE.sub("", slug).strip("-")
    return slug[:MAX_TITLE_LEN] or "note"


def _format_body(title: str, text: str, moment: datetime) -> str:
    return (
        f"# {title}\n\n"
        f"_создано: {moment.isoformat()}_\n\n"
        f"{text}\n"
    )
