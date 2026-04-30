"""Единый контракт утренней sales-рассылки и follow-up отчетов."""

from __future__ import annotations

from typing import Final

SALES_PRIMARY_REPORT: Final[str] = "sales"
SALES_FOLLOWUP_REPORTS: Final[tuple[str, ...]] = ("risks", "focus")
SALES_DISPATCH_SEQUENCE: Final[tuple[str, ...]] = (SALES_PRIMARY_REPORT, *SALES_FOLLOWUP_REPORTS)
SALES_RUNTIME_REPORT_TYPES: Final[frozenset[str]] = frozenset({"sales", "pipeline", "risks", "focus", "weekly"})


def sales_dispatch_sequence(report_type: str) -> tuple[str, ...]:
    normalized = str(report_type or "").strip().lower()
    if normalized == SALES_PRIMARY_REPORT:
        return SALES_DISPATCH_SEQUENCE
    if normalized in SALES_RUNTIME_REPORT_TYPES:
        return (normalized,)
    return (SALES_PRIMARY_REPORT,)


def sales_followup_report_types(report_type: str) -> tuple[str, ...]:
    sequence = sales_dispatch_sequence(report_type)
    if not sequence or sequence[0] != SALES_PRIMARY_REPORT:
        return ()
    return sequence[1:]
