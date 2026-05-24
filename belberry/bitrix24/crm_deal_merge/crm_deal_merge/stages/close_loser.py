"""WRITE-стадия close-loser — закрыть LOSER-сделки после переноса."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient, BitrixError
from ..config import COMMENT_LOSE_TEMPLATE, LOSE_STAGE_38, LOSE_STAGE_50, PORTAL_DOMAIN
from ..domain import normalize_domain
from ..grouping import funnel_id
from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(bx: BitrixClient, sheets: SheetsClient, *, dry_run: bool = False, limit: int | None = None) -> dict:
    groups = [(row, g) for row, g in read_groups(sheets) if g.status == Status.TRANSFERRED]
    if limit:
        groups = groups[:limit]
    now = datetime.now(MOSCOW_TZ)
    counters: Counter[str] = Counter()
    for row_number, group in groups:
        try:
            if dry_run:
                print(f"[close-loser dry-run] {group.company_id}:{group.domain} losers={group.loser_ids}")
                counters["groups"] += 1
                counters["losers"] += len(group.loser_ids)
                continue
            loser_lines = []
            for loser_id in group.loser_ids:
                deal = bx.get_deal(loser_id)
                if not deal:
                    continue
                _assert_title_matches_domain(deal, group.domain)
                deal_funnel = funnel_id(deal)
                if deal_funnel not in ("38", "50"):
                    raise BitrixError(
                        f"LOSER #{loser_id} в воронке {deal_funnel} — close-loser работает только с [38]/[50]"
                    )
                stage = LOSE_STAGE_50 if deal_funnel == "50" else LOSE_STAGE_38
                comment = COMMENT_LOSE_TEMPLATE.format(
                    ts=now.isoformat(timespec="seconds"),
                    winner_id=group.winner_id,
                    portal=PORTAL_DOMAIN,
                    n_acts=group.n_activities_planned,
                    n_tl=group.n_timeline_planned,
                    n_cont=group.n_contacts_planned,
                )
                existing = deal.get("COMMENTS") or ""
                bx.update_deal(loser_id, {"STAGE_ID": stage, "COMMENTS": (existing + comment).strip()})
                loser_lines.append(f"- #{loser_id} https://{PORTAL_DOMAIN}/crm/deal/details/{loser_id}/")
                counters["losers"] += 1
            if group.winner_id and loser_lines:
                bx.add_deal_timeline_comment(
                    group.winner_id,
                    "[{ts} crm_deal_merge]\nК этой сделке привязаны закрытые дубли:\n{losers}\nИтого перенесено: {acts} активностей, {tl} комментариев, {cont} контактов.".format(
                        ts=now.isoformat(timespec="seconds"),
                        losers="\n".join(loser_lines),
                        acts=group.n_activities_planned,
                        tl=group.n_timeline_planned,
                        cont=group.n_contacts_planned,
                    ),
                )
            update_group(sheets, row_number, replace(group, status=Status.MERGED, last_action_at=now, error_message=None))
            counters["groups"] += 1
        except BitrixError as exc:
            update_group(sheets, row_number, replace(group, status=Status.FAILED, last_action_at=now, error_message=str(exc)[:500]))
            counters["failed"] += 1
    print(f"[close-loser] {dict(counters)}")
    return dict(counters)


def _assert_title_matches_domain(deal: dict, expected_domain: str | None) -> None:
    if expected_domain and normalize_domain(str(deal.get("TITLE") or "")) != expected_domain:
        raise BitrixError(f"TITLE safety check failed for deal #{deal.get('ID')}")
