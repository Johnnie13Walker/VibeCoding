"""Стадия discover — найти все группы cross-funnel дублей [38]↔[50]."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..bitrix_client import BitrixClient
from ..config import (
    FUNNEL_LOSER,
    FUNNEL_WINNER,
    PORTAL_DOMAIN,
    TAB_GROUPS,
)
from ..models import GROUP_HEADERS, Group
from ..sheets_client import SheetsClient
from ..state import Status


def _pick_winner(deals50: list[dict]) -> dict:
    """WINNER = сделка [50] с max DATE_MODIFY; tie-break по большему ID."""
    return max(deals50, key=lambda d: (d.get("DATE_MODIFY", ""), int(d.get("ID", "0"))))


def _deal_url(deal_id: str) -> str:
    return f"https://{PORTAL_DOMAIN}/crm/deal/details/{deal_id}/"


def _company_url(company_id: str) -> str:
    return f"https://{PORTAL_DOMAIN}/crm/company/details/{company_id}/"


def _escape(text: str) -> str:
    """Экранирование кавычек для встраивания в HYPERLINK-формулу."""
    return (text or "").replace('"', '""')


def _hlink(url: str, label: str) -> str:
    # Локаль ru_RU → разделитель аргументов формул `;`
    return f'=HYPERLINK("{_escape(url)}";"{_escape(label)}")'


def _stage_map(bx: BitrixClient, category_id: str) -> dict[str, str]:
    """Возвращает {STATUS_ID: NAME} для воронки."""
    stages = bx.call("crm.dealcategory.stage.list", {"id": category_id}).get("result", [])
    return {s["STATUS_ID"]: s.get("NAME", s["STATUS_ID"]) for s in stages}


def run(bx: BitrixClient, sheets: SheetsClient) -> dict:
    """Поиск cross-funnel дублей и запись в Sheets c гиперссылками."""
    print(f"[discover] загружаю воронку [{FUNNEL_LOSER}] Реанимация...")
    deals_38 = bx.list_deals_in_funnel(FUNNEL_LOSER)
    print(f"[discover]   получено {len(deals_38)} сделок")

    print(f"[discover] загружаю воронку [{FUNNEL_WINNER}] Телемаркетинг...")
    deals_50 = bx.list_deals_in_funnel(FUNNEL_WINNER)
    print(f"[discover]   получено {len(deals_50)} сделок")

    print("[discover] подтягиваю stage-карту воронок...")
    stages = {**_stage_map(bx, FUNNEL_LOSER), **_stage_map(bx, FUNNEL_WINNER)}

    by_company_38: dict[str, list[dict]] = defaultdict(list)
    by_company_50: dict[str, list[dict]] = defaultdict(list)
    for d in deals_38:
        cid = d.get("COMPANY_ID")
        if cid and cid != "0":
            by_company_38[cid].append(d)
    for d in deals_50:
        cid = d.get("COMPANY_ID")
        if cid and cid != "0":
            by_company_50[cid].append(d)

    cross = sorted(
        set(by_company_38.keys()) & set(by_company_50.keys()), key=int
    )
    print(f"[discover] cross-funnel групп: {len(cross)}")

    print("[discover] подтягиваю названия компаний (batch)...")
    company_names: dict[str, str] = {}
    for offset in range(0, len(cross), 50):
        chunk = cross[offset : offset + 50]
        cmd = {f"c{cid}": ("crm.company.get", {"id": cid}) for cid in chunk}
        body = bx.batch(cmd)
        for cid in chunk:
            entry = body.get(f"c{cid}")
            company_names[cid] = (entry.get("TITLE") if isinstance(entry, dict) else "") or ""

    sheets.ensure_sheet(TAB_GROUPS)
    sheets.clear(TAB_GROUPS)
    sheets.append(TAB_GROUPS, [GROUP_HEADERS])

    rows: list[list[str]] = []
    winner_closed_cnt = 0
    total_losers = 0

    for cid in cross:
        losers = sorted(by_company_38[cid], key=lambda x: int(x["ID"]))
        winner = _pick_winner(by_company_50[cid])
        winner_closed = winner.get("CLOSED") == "Y"
        if winner_closed:
            winner_closed_cnt += 1
        total_losers += len(losers)

        # Названия для гиперссылок
        cname = company_names.get(cid, f"company #{cid}")
        winner_title = (winner.get("TITLE") or f"deal #{winner['ID']}").strip()
        winner_stage_id = winner.get("STAGE_ID", "")
        winner_stage_name = stages.get(winner_stage_id, winner_stage_id)
        winner_open_mark = "закрыта" if winner_closed else "открыта"
        winner_label = f"{winner_title} — {winner_stage_name} — {winner_open_mark}"

        # Для LOSER берём первого + указание количества (если >1)
        first_loser = losers[0]
        loser_title = (first_loser.get("TITLE") or f"deal #{first_loser['ID']}").strip()
        loser_stage_id = first_loser.get("STAGE_ID", "")
        loser_stage_name = stages.get(loser_stage_id, loser_stage_id)
        loser_label = f"{loser_title} — {loser_stage_name}"
        if len(losers) > 1:
            loser_label += f" (+{len(losers) - 1} ещё)"

        group = Group(
            company_id=cid,
            company_name=cname,
            inn=None,
            domain=None,
            company_link_formula=_hlink(_company_url(cid), cname or f"company #{cid}"),
            winner_id=str(winner["ID"]),
            winner_link_formula=_hlink(_deal_url(str(winner["ID"])), winner_label),
            winner_stage=winner_stage_id,
            winner_stage_name=winner_stage_name,
            winner_closed=winner_closed,
            loser_ids=[str(d["ID"]) for d in losers],
            loser_link_formulas=[_hlink(_deal_url(str(first_loser["ID"])), loser_label)],
            status=Status.NEW,
        )
        rows.append(group.to_sheet_row())

    BATCH = 200
    for off in range(0, len(rows), BATCH):
        sheets.append(TAB_GROUPS, rows[off : off + BATCH], value_input_option="USER_ENTERED")
    print(f"[discover] записано в Sheets: {len(rows)} групп (с гиперссылками)")

    return {
        "groups": len(rows),
        "losers": total_losers,
        "winner_closed_groups": winner_closed_cnt,
        "deals_38_total": len(deals_38),
        "deals_50_total": len(deals_50),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
