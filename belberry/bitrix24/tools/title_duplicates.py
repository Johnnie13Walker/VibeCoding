"""Поиск дублей сделок по точному нормализованному TITLE."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


def normalize_title(title: str) -> str:
    """strip, lower, collapse whitespace."""
    return re.sub(r"\s+", " ", str(title or "").strip().lower())


def find_title_duplicates(deals: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for deal in deals:
        title = normalize_title(str(deal.get("TITLE") or ""))
        if not title:
            continue
        groups.setdefault(title, []).append(deal)

    duplicates = {
        title: sorted(items, key=lambda item: (str(item.get("DATE_CREATE") or ""), str(item.get("ID") or "")))
        for title, items in groups.items()
        if len(items) >= 2
    }
    return dict(sorted(duplicates.items(), key=lambda item: (-len(item[1]), item[0])))
