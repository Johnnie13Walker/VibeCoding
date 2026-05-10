"""Skill: поиск заметок в vault.

Референсный шаблон. Целевой путь в runtime:
``cloudbot/skills/obsidian_search.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .obsidian_provider import ObsidianProvider, SearchHit


@dataclass(frozen=True)
class SearchResult:
    query: str
    hits: list[SearchHit]


def search_notes(provider: ObsidianProvider, query: str, *, limit: int = 10) -> SearchResult:
    """Найти заметки по содержимому и имени файла.

    Перед поиском выполняется `git pull --rebase`, чтобы Cloudbot всегда
    отвечал по самой свежей версии vault.
    """

    cleaned = (query or "").strip()
    if not cleaned:
        raise ValueError("Пустой поисковый запрос")

    provider.ensure_vault()
    provider.sync_pull()

    hits = provider.search_notes(cleaned, limit=limit)
    return SearchResult(query=cleaned, hits=hits)


def format_hits(result: SearchResult) -> str:
    """Краткий текстовый вывод для Telegram-ответа."""
    if not result.hits:
        return f"По запросу «{result.query}» в vault ничего не найдено."
    lines = [f"Найдено по запросу «{result.query}»:"]
    for hit in result.hits:
        lines.append(f"- `{hit.path}` — {hit.snippet}")
    return "\n".join(lines)
