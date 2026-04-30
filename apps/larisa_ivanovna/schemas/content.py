"""Схемы контурa контентных тем."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentTheme:
    id: str
    title: str
    angle: str
    audience: str
    format: str
    evidence: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class ContentPostDraft:
    theme: ContentTheme
    tone: str
    hook: str
    outline: tuple[str, ...]
    post_text: str


@dataclass(frozen=True)
class ContentTopicsDigest:
    date_msk: str
    period_key: str
    period_label: str
    summary: str
    themes: tuple[ContentTheme, ...] = tuple()
    limitations: tuple[str, ...] = tuple()
    commit_count: int = 0
    status_entry_count: int = 0
