"""Стадия discover — READ-ONLY.

1. Загружаем все компании портала через crm.company.list (paginated).
2. Загружаем все реквизиты ENTITY_TYPE_ID=4 одним пагинированным проходом.
3. Подсчитываем n_deals и n_contacts (батчем).
4. Классифицируем: HAS_VALID_INN | EMPTY_INN | NO_REQUISITE.
5. Кросс-чек с листом merge_groups deal-merge — выставляем in_active_deal_merge.
6. Записываем только EMPTY_INN + NO_REQUISITE в лист company_enrich_queue.
7. Идемпотентность: строки status != NEW не перезаписываются.

Ничего не пишет в Bitrix.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    DEAL_MERGE_ACTIVE_STATUSES,
    ENTITY_TYPE_COMPANY,
    TAB_DEAL_MERGE_GROUPS,
)
from ..hyperlinks import company_link
from ..models import (
    CompanyClass,
    CompanyInventory,
    QueueRow,
    classify_company,
    extract_web_url,
    find_uf_inn_candidate,
)
from ..sheet_store import upsert_queue_rows
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(bx: BitrixClient, sheets: SheetsClient, *, limit_companies: int | None = None) -> dict:
    print("[discover] загружаю компании Bitrix24...")
    company_select = list(bx.DEFAULT_COMPANY_SELECT)
    # Добавляем UF-поля, если они есть на портале
    try:
        uf = bx.get_company_user_fields()
        for f in uf:
            field_name = f.get("FIELD_NAME") or f.get("FIELD") or f.get("XML_ID")
            if field_name and str(field_name).startswith("UF_"):
                company_select.append(str(field_name))
    except Exception as exc:  # pragma: no cover — defensive
        print(f"[discover] не удалось получить UF-поля: {exc}; продолжаю без них")
    companies = bx.list_companies(select=company_select)
    if limit_companies:
        companies = companies[:limit_companies]
    print(f"[discover] компаний: {len(companies)}")

    print("[discover] загружаю реквизиты ENTITY_TYPE_ID=4...")
    requisites_all = bx.list_requisites(entity_type_id=ENTITY_TYPE_COMPANY)
    req_by_company: dict[str, list[dict]] = defaultdict(list)
    for r in requisites_all:
        entity_id = str(r.get("ENTITY_ID") or "")
        if entity_id:
            req_by_company[entity_id].append(r)
    print(f"[discover] реквизитов: {len(requisites_all)}; компаний с реквизитами: {len(req_by_company)}")

    active_merge_company_ids = _load_active_merge_company_ids(sheets)
    print(f"[discover] компаний в активном merge: {len(active_merge_company_ids)}")

    inventories: list[CompanyInventory] = []
    counts = {"has_valid_inn": 0, "empty_inn": 0, "no_requisite": 0}
    for company in companies:
        cid = str(company.get("ID") or "")
        if not cid:
            continue
        inv = CompanyInventory(
            company_id=cid,
            title=str(company.get("TITLE") or ""),
            web=extract_web_url(company.get("WEB")),
            uf_inn_candidate=find_uf_inn_candidate(company),
            requisites=req_by_company.get(cid, []),
        )
        counts[inv.classification().value] += 1
        inventories.append(inv)

    candidates = [inv for inv in inventories if inv.classification() in {CompanyClass.EMPTY_INN, CompanyClass.NO_REQUISITE}]
    print(f"[discover] кандидатов на enrich: {len(candidates)}")

    # n_deals / n_contacts только для кандидатов — экономим API
    deals_counts, contacts_counts = _load_counts(bx, [c.company_id for c in candidates])
    for inv in candidates:
        inv.n_deals = deals_counts.get(inv.company_id, 0)
        inv.n_contacts = contacts_counts.get(inv.company_id, 0)

    rows = [
        QueueRow(
            company_id=inv.company_id,
            company_name=inv.title,
            current_inn=inv.current_inn(),
            web=inv.web,
            uf_inn_candidate=inv.uf_inn_candidate,
            n_deals=inv.n_deals,
            n_contacts=inv.n_contacts,
            in_active_deal_merge=inv.company_id in active_merge_company_ids,
            status=Status.NEW,
            priority=inv.n_deals + inv.n_contacts,
            company_link_formula=company_link(inv.company_id, inv.title or f"company #{inv.company_id}"),
        )
        for inv in candidates
    ]
    rows.sort(key=lambda r: r.priority, reverse=True)

    summary_upsert = upsert_queue_rows(sheets, rows)
    print(f"[discover] queue upsert: {summary_upsert}")

    return {
        "companies_total": len(companies),
        "classification": counts,
        "candidates": len(candidates),
        "active_merge_skipped_visible": sum(1 for r in rows if r.in_active_deal_merge),
        "queue": summary_upsert,
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
    }


def _load_active_merge_company_ids(sheets: SheetsClient) -> set[str]:
    """Прочитать лист merge_groups deal-merge модуля и собрать company_id с активным статусом."""
    try:
        rows = sheets.read(TAB_DEAL_MERGE_GROUPS)
    except Exception as exc:  # pragma: no cover — лист может отсутствовать на dev-портале
        print(f"[discover] лист {TAB_DEAL_MERGE_GROUPS} недоступен: {exc}; считаем что активных merge нет")
        return set()
    if not rows:
        return set()
    headers = [str(x) for x in rows[0]]
    try:
        cid_idx = headers.index("company_id")
        status_idx = headers.index("status")
    except ValueError:
        return set()
    out: set[str] = set()
    for raw in rows[1:]:
        if len(raw) <= max(cid_idx, status_idx):
            continue
        cid = str(raw[cid_idx]).strip()
        status = str(raw[status_idx]).strip().upper()
        if cid and status in DEAL_MERGE_ACTIVE_STATUSES:
            out.add(cid)
    return out


def _load_counts(bx: BitrixClient, company_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Подсчитать n_deals и n_contacts батчами по 50."""
    deals_counts: dict[str, int] = {}
    contacts_counts: dict[str, int] = {}
    for offset in range(0, len(company_ids), 50):
        chunk = company_ids[offset : offset + 50]
        commands: dict[str, tuple[str, dict]] = {}
        for cid in chunk:
            commands[f"d{cid}"] = (
                "crm.deal.list",
                {"filter": {"COMPANY_ID": cid}, "select": ["ID"], "start": -1},
            )
            commands[f"c{cid}"] = ("crm.company.contact.items.get", {"id": cid})
        body = bx.batch(commands)
        for cid in chunk:
            d = body.get(f"d{cid}") or []
            c = body.get(f"c{cid}") or []
            deals_counts[cid] = len(d) if isinstance(d, list) else 0
            contacts_counts[cid] = len(c) if isinstance(c, list) else 0
    return deals_counts, contacts_counts
