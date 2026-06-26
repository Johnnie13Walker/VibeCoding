"""Привязка контактов-сирот к компаниям/сделкам по телефону.

Импорт «Вернувшийся клиент» (SOURCE_ID=5, 26.05.2026) создал ~3.7k контактов
без компании. Эта стадия матчит сироту по телефону к существующей компании
(напрямую через crm.duplicate.findbycomm или через контакт с тем же телефоном)
и привязывает контакт к компании + её открытым сделкам.

Только ADD-операции: ничего не удаляем и не отвязываем. Дедуп получившихся
дублей — отдельной стадией (dedupe_contacts), уже защищённой от удаления
контактов на сделках вне телемаркетинга.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    CONTACT_REBIND_SHEET_TAB,
    CONTACT_REBIND_SOURCE_IDS,
    PORTAL_DOMAIN,
    SERVICE_ACCOUNT_JSON,
    SHEET_ID,
)
from ..sheets_client import SheetsClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

REPORT_HEADERS = [
    "timestamp",
    "contact_id",
    "contact_name",
    "phones",
    "status",
    "target_company_id",
    "target_company_title",
    "target_deal_ids",
    "candidates",
    "contact_link",
]

# Явный мусор из импорта — не привязываем (служебные/пустые карточки).
_JUNK_NAME_TOKENS = ("битрикс24", "bitrix24", "no-reply", "noreply", "тест", "test")


@dataclass
class RebindOutcome:
    contact_id: str
    contact_name: str = ""
    phones: list[str] = field(default_factory=list)
    status: str = ""
    target_company_id: str = ""
    target_company_title: str = ""
    target_deal_ids: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)


def run_batch(
    bx: BitrixClient,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    sources: list[str] | None = None,
    write_report: bool = True,
) -> dict:
    sources = sources or CONTACT_REBIND_SOURCE_IDS
    orphans = _iter_orphans(bx, sources=sources, limit=limit)
    outcomes = [_plan_one(bx, contact) for contact in orphans]

    if not dry_run:
        for outcome in outcomes:
            if outcome.status in {"MATCH_COMPANY", "MATCH_VIA_CONTACT"} and outcome.target_company_id:
                _apply_one(bx, outcome)

    if write_report and outcomes:
        try:
            _write_report(outcomes, dry_run=dry_run)
        except Exception:  # noqa: BLE001 — отчёт не должен ронять прогон
            pass

    return _summary(outcomes, dry_run=dry_run)


def _iter_orphans(bx: BitrixClient, *, sources: list[str], limit: int | None) -> list[dict]:
    contacts = bx.list_contacts(
        filter={"SOURCE_ID": sources, "COMPANY_ID": 0},
        select=["ID", "NAME", "LAST_NAME", "SECOND_NAME", "PHONE", "EMAIL", "SOURCE_ID"],
    )
    if limit is not None:
        contacts = contacts[:limit]
    return contacts


def _plan_one(bx: BitrixClient, contact: dict) -> RebindOutcome:
    contact_id = str(contact.get("ID") or "")
    outcome = RebindOutcome(
        contact_id=contact_id,
        contact_name=_display_name(contact),
        phones=sorted(_normalize_phones(contact)),
    )

    if _is_junk(contact):
        outcome.status = "JUNK"
        return outcome
    if not outcome.phones:
        outcome.status = "NO_PHONE"
        return outcome

    company_ids: set[str] = set()
    for phone in outcome.phones:
        for query in _bitrix_phone_queries(phone):
            company_ids.update(bx.find_by_comm("PHONE", query, "COMPANY"))

    match_status = "MATCH_COMPANY"
    if not company_ids:
        # Косвенно: телефон есть у другого контакта → берём его компанию.
        for phone in outcome.phones:
            for query in _bitrix_phone_queries(phone):
                for other_id in bx.find_by_comm("PHONE", query, "CONTACT"):
                    if str(other_id) == contact_id:
                        continue
                    company_ids.update(bx.list_contact_companies(str(other_id)))
        match_status = "MATCH_VIA_CONTACT"

    company_ids.discard("")
    outcome.candidates = sorted(company_ids)

    if not company_ids:
        outcome.status = "NO_MATCH"
        return outcome
    if len(company_ids) > 1:
        outcome.status = "AMBIGUOUS"
        return outcome

    company_id = next(iter(company_ids))
    outcome.status = match_status
    outcome.target_company_id = company_id
    company = bx.get_company(company_id) or {}
    outcome.target_company_title = str(company.get("TITLE") or "")
    outcome.target_deal_ids = _open_deal_ids(bx, company_id)
    return outcome


def _apply_one(bx: BitrixClient, outcome: RebindOutcome) -> None:
    bx.update_contact(outcome.contact_id, {"COMPANY_ID": outcome.target_company_id})
    bx.add_contact_company_relation(outcome.contact_id, outcome.target_company_id)
    for deal_id in outcome.target_deal_ids:
        existing = {
            str(item.get("CONTACT_ID") or item.get("ID") or "")
            for item in bx.list_deal_contacts(deal_id)
            if isinstance(item, dict)
        }
        if outcome.contact_id not in existing:
            bx.add_deal_contact(deal_id, outcome.contact_id)


def _open_deal_ids(bx: BitrixClient, company_id: str) -> list[str]:
    ids: list[str] = []
    for deal in bx.list_company_deals(company_id):
        if str(deal.get("CLOSED") or "").upper() == "Y":
            continue
        deal_id = str(deal.get("ID") or "")
        if deal_id:
            ids.append(deal_id)
    return ids


def _is_junk(contact: dict) -> bool:
    blob = " ".join(
        _clean(contact.get(k)) for k in ("LAST_NAME", "NAME", "SECOND_NAME")
    ).lower()
    for item in contact.get("EMAIL") or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        blob += " " + _clean(value).lower()
    return any(token in blob for token in _JUNK_NAME_TOKENS)


def _display_name(contact: dict) -> str:
    parts = [_clean(contact.get(k)) for k in ("LAST_NAME", "NAME", "SECOND_NAME")]
    return " ".join(p for p in parts if p).strip()


def _normalize_phones(contact: dict) -> set[str]:
    out: set[str] = set()
    for item in contact.get("PHONE") or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        digits = re.sub(r"\D+", "", _clean(value))
        if len(digits) >= 10:
            out.add(digits[-10:])
    return out


def _bitrix_phone_queries(digits10: str) -> tuple[str, str]:
    """Форматы телефона, которые матчит Bitrix `crm.duplicate.findbycomm`.

    `_normalize_phones` хранит последние 10 цифр (для сравнения/отчёта), но Bitrix
    ищет дубли по своему формату хранения и НЕ матчит голые 10 цифр против
    сохранённого `+7XXXXXXXXXX` (проверено на проде: `find_by_comm("4993929971")`
    → [], `find_by_comm("+74993929971")` → [компания]). Поэтому в lookup передаём
    обе российские формы — `+7…` и `8…`.
    """
    return (f"+7{digits10}", f"8{digits10}")


def _write_report(outcomes: list[RebindOutcome], *, dry_run: bool) -> None:
    sheets = SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)
    sheets.ensure_sheet(CONTACT_REBIND_SHEET_TAB)
    if not sheets.read(CONTACT_REBIND_SHEET_TAB, "A1:J1"):
        sheets.update(CONTACT_REBIND_SHEET_TAB, "A1:J1", [REPORT_HEADERS])
    now = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
    rows = [
        [
            now,
            o.contact_id,
            o.contact_name,
            ", ".join(o.phones),
            o.status if dry_run else f"{o.status} (applied)",
            o.target_company_id,
            o.target_company_title,
            ", ".join(o.target_deal_ids),
            ", ".join(o.candidates),
            f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/contact/details/{o.contact_id}/";"contact {o.contact_id}")',
        ]
        for o in outcomes
    ]
    sheets.append(CONTACT_REBIND_SHEET_TAB, rows, value_input_option="USER_ENTERED")


def _summary(outcomes: list[RebindOutcome], *, dry_run: bool) -> dict:
    by_status: dict[str, int] = {}
    for o in outcomes:
        by_status[o.status] = by_status.get(o.status, 0) + 1
    return {
        "dry_run": dry_run,
        "total": len(outcomes),
        "by_status": by_status,
        "rebindable": sum(
            1 for o in outcomes if o.status in {"MATCH_COMPANY", "MATCH_VIA_CONTACT"}
        ),
        "outcomes": [o.__dict__ for o in outcomes],
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
