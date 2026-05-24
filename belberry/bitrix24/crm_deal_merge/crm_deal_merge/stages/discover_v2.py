"""Стадия discover-v2 — группировка [38]+[50] по (company_id, domain)."""
from __future__ import annotations

from datetime import datetime

from ..bitrix_client import BitrixClient
from ..config import FUNNEL_LOSER, FUNNEL_WINNER
from ..grouping import group_deals
from ..hyperlinks import company_link, deal_link
from ..models import Group
from ..sheet_store import write_groups
from ..sheets_client import SheetsClient
from ..state import Status

DEAL_SELECT = ["ID", "CATEGORY_ID", "COMPANY_ID", "STAGE_ID", "TITLE", "DATE_MODIFY", "DATE_CREATE", "CLOSED"]


def run(bx: BitrixClient, sheets: SheetsClient) -> dict:
    print("[discover-v2] загружаю сделки [38]+[50]...")
    deals = []
    for funnel in (FUNNEL_LOSER, FUNNEL_WINNER):
        part = bx.list_deals_in_funnel(funnel, select=DEAL_SELECT)
        print(f"[discover-v2] воронка [{funnel}]: {len(part)} сделок")
        deals.extend(part)

    print("[discover-v2] группирую по (company_id, normalized_domain)...")
    deal_groups, orphans = group_deals(deals)
    company_ids = sorted({g.company_id for g in deal_groups}, key=_int_key)
    company_meta = _load_company_meta(bx, company_ids)
    stages = {**_stage_map(bx, FUNNEL_LOSER), **_stage_map(bx, FUNNEL_WINNER)}

    rows: list[Group] = []
    candidates = 0
    manual = 0
    ok_as_is = 0
    total_losers = 0
    for item in deal_groups:
        meta = company_meta.get(item.company_id, {})
        if item.manual:
            manual += 1
            rows.append(
                Group(
                    company_id=item.company_id,
                    company_name=meta.get("title", ""),
                    inn=meta.get("inn") or "—",
                    domain=item.domain,
                    winner_id=None,
                    winner_stage=None,
                    winner_stage_name=None,
                    winner_closed=False,
                    loser_ids=[],
                    n_total=len(item.deals),
                    n_winner=0,
                    company_link_formula=company_link(item.company_id, meta.get("title") or f"company #{item.company_id}"),
                    status=Status.MANUAL,
                    error_message="domain=None или меньше 2 сделок",
                )
            )
            continue
        if not item.losers:
            ok_as_is += 1
            continue
        candidates += 1
        total_losers += len(item.losers)
        winner = item.winner or {}
        winner_id = str(winner.get("ID") or "")
        winner_stage = str(winner.get("STAGE_ID") or "")
        winner_stage_name = stages.get(winner_stage, winner_stage)
        winner_closed = str(winner.get("CLOSED") or "").upper() == "Y"
        rows.append(
            Group(
                company_id=item.company_id,
                company_name=meta.get("title", ""),
                inn=meta.get("inn") or "—",
                domain=item.domain,
                winner_id=winner_id,
                winner_stage=winner_stage,
                winner_stage_name=winner_stage_name,
                winner_closed=winner_closed,
                loser_ids=[str(d["ID"]) for d in item.losers],
                n_total=len(item.deals),
                n_winner=1,
                company_link_formula=company_link(item.company_id, meta.get("title") or f"company #{item.company_id}"),
                winner_link_formula=deal_link(winner_id, _deal_label(winner, winner_stage_name)),
                loser_link_formulas=[deal_link(str(d["ID"]), _deal_label(d, stages.get(str(d.get("STAGE_ID") or ""), str(d.get("STAGE_ID") or "")))) for d in item.losers[:5]],
                status=Status.NEW,
            )
        )

    write_groups(sheets, rows)
    print(f"[discover-v2] записано групп-кандидатов: {candidates}; MANUAL: {manual}; orphans: {len(orphans)}")
    return {
        "groups_written": len(rows),
        "candidates": candidates,
        "manual": manual,
        "ok_as_is": ok_as_is,
        "losers": total_losers,
        "orphans": len(orphans),
        "deals_total": len(deals),
        "ts_msk": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _load_company_meta(bx: BitrixClient, company_ids: list[str]) -> dict[str, dict[str, str]]:
    meta = {cid: {"title": "", "inn": "—"} for cid in company_ids}
    for off in range(0, len(company_ids), 50):
        chunk = company_ids[off : off + 50]
        commands = {f"c{cid}": ("crm.company.get", {"id": cid}) for cid in chunk}
        body = bx.batch(commands)
        for cid in chunk:
            company = body.get(f"c{cid}")
            if isinstance(company, dict):
                meta[cid]["title"] = str(company.get("TITLE") or "")
    for off in range(0, len(company_ids), 50):
        chunk = company_ids[off : off + 50]
        commands = {
            f"r{cid}": (
                "crm.requisite.list",
                {"filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": cid}, "select": ["ID", "RQ_INN", "ENTITY_ID"]},
            )
            for cid in chunk
        }
        body = bx.batch(commands)
        for cid in chunk:
            rows = body.get(f"r{cid}") or []
            if isinstance(rows, list) and rows:
                inn = rows[0].get("RQ_INN")
                if inn:
                    meta[cid]["inn"] = str(inn)
    return meta


def _stage_map(bx: BitrixClient, category_id: str) -> dict[str, str]:
    stages = bx.call("crm.dealcategory.stage.list", {"id": category_id}).get("result", [])
    return {s["STATUS_ID"]: s.get("NAME", s["STATUS_ID"]) for s in stages if isinstance(s, dict) and s.get("STATUS_ID")}


def _deal_label(deal: dict, stage_name: str) -> str:
    closed = "закрыта" if str(deal.get("CLOSED") or "").upper() == "Y" else "открыта"
    return f"{deal.get('TITLE') or 'deal #' + str(deal.get('ID'))} — {stage_name} — {closed}"


def _int_key(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
