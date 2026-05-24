"""Read-only аудит компаний-пустышек в Bitrix24."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import PORTAL_DOMAIN
from ..sheets_client import SheetsClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
TAB_EMPTY_COMPANIES = "Пустые компании"
TARGET_SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"

HEADERS = [
    "Компания (название, гиперссылка в Б24)",
    "Ответственный",
    "ИНН",
    "Оборот компании",
    "Дата создания",
    "Дата изменения",
    "Контактов",
    "Сделок",
    "Лидов",
    "Телефон в карточке",
    "Email в карточке",
    "Комментарий",
    "company_id",
    "Категория мусора",
    "Причина",
    "Полезных контактов",
    "Мусорных контактов",
    "ID мусорных контактов",
]


def run(bx: BitrixClient, sheets: SheetsClient, *, write_sheet: bool = True) -> dict[str, Any]:
    started = datetime.now(MOSCOW_TZ)
    previous_rows = _count_existing_rows(sheets)
    companies = _load_companies(bx)
    contacts = _load_contacts(bx)
    contact_counts, contacts_by_company = _index_contacts(contacts)
    deals = _load_records(bx, "crm.deal.list", ["ID", "COMPANY_ID", "CONTACT_ID"], "сделки")
    leads = _load_records(bx, "crm.lead.list", ["ID", "COMPANY_ID", "CONTACT_ID"], "лиды")
    deal_counts = _count_records_by_company(deals)
    lead_counts = _count_records_by_company(leads)
    contact_deal_counts = _count_records_by_contact(deals)
    contact_lead_counts = _count_records_by_contact(leads)
    inns = _load_inns(bx)

    candidates = []
    for company in companies:
        company_id = str(company.get("ID") or "")
        if deal_counts[company_id] or lead_counts[company_id]:
            continue
        contact_audit = _audit_company_contacts(
            contacts_by_company.get(company_id, []),
            contact_deal_counts,
            contact_lead_counts,
        )
        if contact_audit["useful_count"]:
            continue
        category = "без контактов" if not contact_audit["junk_count"] else "только мусорные контакты"
        reason = (
            "нет связанных контактов, сделок и лидов"
            if category == "без контактов"
            else "все связанные контакты без имени/должности/email и без собственных сделок/лидов"
        )
        candidates.append((company, category, reason, contact_audit))

    users = _load_users(bx, {str(c.get("ASSIGNED_BY_ID") or "") for c, *_ in candidates})

    rows = [
        [
            f"Отчёт обновлён: {started.isoformat(timespec='seconds')} МСК",
            (
                "Критерий: сделок=0, лидов=0, и либо контактов=0, либо все контакты мусорные. "
                "Телефоны/комментарии в карточке компании не считаются полезным контактом. "
                "Bitrix read-only, запись только в Google Sheets."
            ),
        ],
        HEADERS,
    ]
    for company, category, reason, contact_audit in sorted(candidates, key=lambda item: _company_sort_key(item[0]), reverse=True):
        company_id = str(company.get("ID") or "")
        title = str(company.get("TITLE") or "").strip() or f"company #{company_id}"
        rows.append(
            [
                _company_link(company_id, title),
                users.get(str(company.get("ASSIGNED_BY_ID") or ""), str(company.get("ASSIGNED_BY_ID") or "")),
                inns.get(company_id, ""),
                _clean(company.get("REVENUE")),
                _date(company.get("DATE_CREATE")),
                _date(company.get("DATE_MODIFY")),
                str(contact_counts[company_id]),
                str(deal_counts[company_id]),
                str(lead_counts[company_id]),
                _sheet_text(_multi(company.get("PHONE"))),
                _sheet_text(_multi(company.get("EMAIL"))),
                _sheet_text(_clean(company.get("COMMENTS"))),
                company_id,
                category,
                reason,
                str(contact_audit["useful_count"]),
                str(contact_audit["junk_count"]),
                ", ".join(contact_audit["junk_ids"]),
            ]
        )

    if write_sheet:
        sheets.ensure_sheet(TAB_EMPTY_COMPANIES)
        sheets.clear(TAB_EMPTY_COMPANIES)
        sheets.update(TAB_EMPTY_COMPANIES, "A1", rows, value_input_option="USER_ENTERED")
    else:
        print("[empty-companies dry-run] Google Sheets не обновляю")

    return {
        "tab": TAB_EMPTY_COMPANIES,
        "dry_run": not write_sheet,
        "companies_total": len(companies),
        "trash_companies": len(candidates),
        "previous_snapshot_rows": previous_rows,
        "delta_vs_previous": len(candidates) - previous_rows if previous_rows is not None else None,
        "new_vs_previous": max(len(candidates) - previous_rows, 0) if previous_rows is not None else None,
        "gone_vs_previous": max(previous_rows - len(candidates), 0) if previous_rows is not None else None,
        "without_contacts": sum(1 for _, category, _, _ in candidates if category == "без контактов"),
        "with_only_junk_contacts": sum(1 for _, category, _, _ in candidates if category == "только мусорные контакты"),
        "contacts_with_company_total": sum(contact_counts.values()),
        "deals_with_company_total": sum(deal_counts.values()),
        "leads_with_company_total": sum(lead_counts.values()),
        "updated_at_msk": started.isoformat(timespec="seconds"),
    }


def _count_existing_rows(sheets: SheetsClient) -> int | None:
    try:
        rows = sheets.read(TAB_EMPTY_COMPANIES, "A1:R20000", unformatted=True)
    except Exception as exc:  # noqa: BLE001 - отсутствие листа не должно валить dry-run
        print(f"[empty-companies] не удалось прочитать текущий снапшот: {exc}")
        return None
    if len(rows) <= 2:
        return 0
    headers = [str(h) for h in rows[1]]
    try:
        company_id_idx = headers.index("company_id")
    except ValueError:
        company_id_idx = 12
    return sum(
        1
        for row in rows[2:]
        if len(row) > company_id_idx and str(row[company_id_idx] or "").strip()
    )


def _load_companies(bx: BitrixClient) -> list[dict]:
    print("[empty-companies] выгружаю компании...")
    companies = list(
        bx.paginate(
            "crm.company.list",
            {
                "select": [
                    "ID",
                    "TITLE",
                    "ASSIGNED_BY_ID",
                    "DATE_CREATE",
                    "DATE_MODIFY",
                    "REVENUE",
                    "PHONE",
                    "EMAIL",
                    "COMMENTS",
                ],
            },
        )
    )
    print(f"[empty-companies] компаний: {len(companies)}")
    return companies


def _load_contacts(bx: BitrixClient) -> list[dict]:
    print("[empty-companies] выгружаю контакты...")
    contacts = list(
        bx.paginate(
            "crm.contact.list",
            {
                "select": [
                    "ID",
                    "COMPANY_ID",
                    "NAME",
                    "SECOND_NAME",
                    "LAST_NAME",
                    "POST",
                    "PHONE",
                    "EMAIL",
                ],
            },
        )
    )
    print(f"[empty-companies] контактов: {len(contacts)}")
    return contacts


def _load_records(
    bx: BitrixClient,
    method: str,
    select: list[str],
    label: str,
) -> list[dict]:
    print(f"[empty-companies] выгружаю {label}...")
    records = list(bx.paginate(method, {"select": select}))
    print(f"[empty-companies] {label}: {len(records)}")
    return records


def _index_contacts(contacts: list[dict]) -> tuple[Counter[str], dict[str, list[dict]]]:
    counts: Counter[str] = Counter()
    by_company: dict[str, list[dict]] = defaultdict(list)
    for contact in contacts:
        for company_id in _company_ids(contact.get("COMPANY_ID")):
            counts[company_id] += 1
            by_company[company_id].append(contact)
    print(f"[empty-companies] контактов с компанией: {sum(counts.values())}")
    return counts, by_company


def _count_records_by_company(records: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in records:
        for company_id in _company_ids(item.get("COMPANY_ID")):
            counts[company_id] += 1
    return counts


def _count_records_by_contact(records: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in records:
        contact_id = str(item.get("CONTACT_ID") or "").strip()
        if contact_id and contact_id != "0":
            counts[contact_id] += 1
    return counts


def _audit_company_contacts(
    contacts: list[dict],
    contact_deal_counts: Counter[str],
    contact_lead_counts: Counter[str],
) -> dict[str, Any]:
    useful_count = 0
    junk_ids: list[str] = []
    for contact in contacts:
        contact_id = str(contact.get("ID") or "").strip()
        if _is_junk_contact(contact, contact_deal_counts[contact_id], contact_lead_counts[contact_id]):
            junk_ids.append(contact_id)
        else:
            useful_count += 1
    return {
        "useful_count": useful_count,
        "junk_count": len(junk_ids),
        "junk_ids": junk_ids,
    }


def _is_junk_contact(contact: dict, deal_count: int, lead_count: int) -> bool:
    if deal_count or lead_count:
        return False
    if _multi(contact.get("EMAIL")):
        return False
    full_name = " ".join(
        _clean(contact.get(part))
        for part in ("LAST_NAME", "NAME", "SECOND_NAME")
        if _clean(contact.get(part))
    ).strip()
    post = _clean(contact.get("POST")).lower().replace("ё", "е")
    no_real_name = not full_name or _is_placeholder_name(full_name)
    no_real_post = not post or post in {"не заполнено", "не заполнен", "нет", "-"}
    return no_real_name and no_real_post


def _is_placeholder_name(value: str) -> bool:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower().replace("ё", "е"))
    return text in {"без имени", "не заполнено", "не указан", "нет имени", "-"}


def _load_inns(bx: BitrixClient) -> dict[str, str]:
    print("[empty-companies] выгружаю реквизиты/ИНН...")
    inns: dict[str, str] = {}
    for req in bx.paginate(
        "crm.requisite.list",
        {
            "filter": {"ENTITY_TYPE_ID": 4},
            "select": ["ID", "ENTITY_ID", "RQ_INN"],
        },
    ):
        company_id = str(req.get("ENTITY_ID") or "").strip()
        inn = str(req.get("RQ_INN") or "").strip()
        if company_id and inn and company_id not in inns:
            inns[company_id] = inn
    print(f"[empty-companies] ИНН найдено: {len(inns)}")
    return inns


def _load_users(bx: BitrixClient, user_ids: set[str]) -> dict[str, str]:
    ids = sorted(uid for uid in user_ids if uid and uid != "0")
    users: dict[str, str] = {}
    for off in range(0, len(ids), 50):
        chunk = ids[off : off + 50]
        body = bx.batch({f"u_{uid}": ("user.get", {"ID": uid}) for uid in chunk})
        for uid in chunk:
            result = body.get(f"u_{uid}") or []
            if isinstance(result, list) and result:
                user = result[0]
                name = " ".join(
                    part for part in [str(user.get("NAME") or ""), str(user.get("LAST_NAME") or "")]
                    if part
                ).strip()
                users[uid] = name or uid
    return users


def _company_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        values = [raw]
    out = []
    for value in values:
        company_id = str(value or "").strip()
        if company_id and company_id != "0":
            out.append(company_id)
    return out


def _company_link(company_id: str, title: str) -> str:
    safe_title = title.replace('"', '""')
    return f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/company/details/{company_id}/";"{safe_title}")'


def _company_sort_key(company: dict) -> tuple[str, int]:
    date_create = str(company.get("DATE_CREATE") or "")
    try:
        company_id = int(str(company.get("ID") or "0"))
    except ValueError:
        company_id = 0
    return date_create, company_id


def _multi(raw: Any) -> str:
    if not raw:
        return ""
    if not isinstance(raw, list):
        return _clean(raw)
    values = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("VALUE") or item.get("value") or ""
        else:
            value = item
        text = str(value or "").strip()
        if text:
            values.append(text)
    return " | ".join(values)


def _clean(raw: Any) -> str:
    if raw is None or raw is False:
        return ""
    if isinstance(raw, (list, dict)):
        return _multi(raw)
    return str(raw).strip()


def _date(raw: Any) -> str:
    text = _clean(raw)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y")
    except ValueError:
        return text


def _sheet_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
