"""Skill: добавить запись в дневную заметку (Daily/YYYY-MM-DD.md).

Референсный шаблон. Целевой путь в runtime:
``cloudbot/skills/obsidian_append_daily.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .obsidian_provider import ObsidianProvider


@dataclass(frozen=True)
class AppendDailyResult:
    relative_path: str
    appended_at: datetime


def append_daily(
    provider: ObsidianProvider,
    raw_text: str,
    *,
    when: datetime | None = None,
) -> AppendDailyResult:
    """Дописать блок в дневную заметку по МСК.

    Если файл `Daily/YYYY-MM-DD.md` ещё не существует, он создаётся
    с базовым заголовком, после чего добавляется блок с временной меткой.
    """

    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Пустая запись")

    provider.ensure_vault()
    provider.sync_pull()

    moment = when or provider.now_local()
    relative_path = provider.daily_relative_path(moment)

    try:
        provider.read_note(relative_path)
    except Exception:
        provider.write_note(relative_path, f"# {moment.strftime('%Y-%m-%d')}\n")

    block = f"## {moment.strftime('%H:%M')}\n\n{text}"
    provider.append_note(relative_path, block)
    provider.sync_push(f"obsidian: запись в дневник {relative_path}")

    return AppendDailyResult(relative_path=relative_path, appended_at=moment)
