"""Статусы строк в очереди company_enrich_queue.

Простой state-machine — линейный pipeline: NEW → ENRICHED|ENRICH_FAILED →
CLASSIFIED → APPROVED → APPLIED|MERGED → VERIFIED|FAILED → DONE.

Write-стадии (APPLIED, MERGED, VERIFIED, DONE, ROLLED_BACK) сейчас не
используются кодом — see stages/apply.py, stages/merge_dupes.py.
"""
from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    NEW = "NEW"
    ENRICHED = "ENRICHED"
    ENRICH_FAILED = "ENRICH_FAILED"
    CLASSIFIED = "CLASSIFIED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"          # реквизит создан (CREATE_REQ путь)
    MERGED = "MERGED"            # компания смержена с дубликатом (MERGE_INTO путь)
    SKIPPED = "SKIPPED"          # уже было правильно (SKIP_ALREADY)
    VERIFIED = "VERIFIED"
    DONE = "DONE"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


# Линейный порядок (для идемпотентности): не понижаем статус строки при повторных запусках
ORDER: dict[Status, int] = {
    Status.NEW: 0,
    Status.ENRICH_FAILED: 1,
    Status.ENRICHED: 2,
    Status.CLASSIFIED: 3,
    Status.APPROVED: 4,
    Status.APPLIED: 5,
    Status.MERGED: 5,
    Status.SKIPPED: 5,
    Status.FAILED: 5,
    Status.VERIFIED: 6,
    Status.DONE: 7,
    Status.ROLLED_BACK: 8,
}


def is_at_least(current: Status, target: Status) -> bool:
    """True, если current уже прошла стадию target (или равна ей).

    Используется для idempotency-чеков: «classify пропускает строки >= CLASSIFIED».
    """
    return ORDER[current] >= ORDER[target]
