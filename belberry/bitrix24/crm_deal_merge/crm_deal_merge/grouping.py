"""Чистая логика группировки сделок [38]+[50]."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .config import FUNNEL_LOSER, FUNNEL_WINNER
from .domain import normalize_domain


@dataclass(frozen=True)
class DealGroup:
    company_id: str
    domain: str | None
    winner: dict | None
    losers: list[dict]
    deals: list[dict]
    manual: bool = False


def group_deals(deals: list[dict]) -> tuple[list[DealGroup], list[dict]]:
    grouped: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    orphans: list[dict] = []
    for deal in deals:
        company_id = str(deal.get("COMPANY_ID") or "").strip()
        if not company_id or company_id == "0":
            orphans.append(deal)
            continue
        grouped[(company_id, normalize_domain(str(deal.get("TITLE") or "")))].append(deal)

    out: list[DealGroup] = []
    for (company_id, domain), items in sorted(grouped.items(), key=_group_sort_key):
        if domain is None or len(items) < 2:
            out.append(DealGroup(company_id, domain, None, [], items, manual=True))
            continue
        winner = pick_winner(items)
        losers = [d for d in sorted(items, key=lambda x: int(str(x.get("ID") or 0))) if d is not winner]
        out.append(DealGroup(company_id, domain, winner, losers, items, manual=False))
    return out, orphans


def pick_winner(deals: list[dict]) -> dict:
    deals_50 = [d for d in deals if funnel_id(d) == FUNNEL_WINNER]
    candidates = deals_50 or [d for d in deals if funnel_id(d) == FUNNEL_LOSER] or deals
    return max(candidates, key=lambda d: (str(d.get("DATE_MODIFY") or ""), int(str(d.get("ID") or 0))))


def funnel_id(deal: dict) -> str:
    stage = str(deal.get("STAGE_ID") or "")
    if stage.startswith("C") and ":" in stage:
        return stage[1:].split(":", 1)[0]
    return str(deal.get("CATEGORY_ID") or "")


def _group_sort_key(item: tuple[tuple[str, str | None], list[dict]]) -> tuple[int, str]:
    (company_id, domain), _ = item
    try:
        cid = int(company_id)
    except ValueError:
        cid = 0
    return cid, domain or ""
