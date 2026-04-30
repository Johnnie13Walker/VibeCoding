"""Схемы входа/выхода финансового контура."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FinanceSource:
    name: str
    source_type: str
    location: str
    access_status: str
    notes: str = ""


@dataclass(frozen=True)
class FinanceSourceSnapshot:
    sources: tuple[FinanceSource, ...] = ()
    google_docs_access_ready: bool = False
    google_sheets_access_ready: bool = False
    missing_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinanceRequest:
    question: str
    focus: str
    period_label: str
    metrics: dict[str, Any] = field(default_factory=dict)
    sources: tuple[str | dict[str, Any], ...] = ()
    facts: tuple[str, ...] = ()
