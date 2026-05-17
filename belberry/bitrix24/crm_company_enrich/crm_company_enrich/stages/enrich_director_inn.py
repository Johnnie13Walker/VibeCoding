"""Обогащение контакта директора ИНН физлица из rusprofile."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import (
    CONTACT_PERSONAL_INN_FIELD,
    LOG_DIR,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_OPEN_STAGES,
)
from ..rusprofile_director import _normalize_full_name, parse_director_from_rusprofile_html
from .sync_deals import _fetch_rusprofile_html

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
CONTACT_OWNER_TYPE_ID = 3
CSV_HEADERS = [
    "timestamp",
    "company_id",
    "director_inn",
    "director_full_name",
    "matched_contact_id",
    "status",
    "skipped_reason",
]


@dataclass
class DirectorInnOutcome:
    company_id: str
    director_inn: str = ""
    director_full_name: str = ""
    matched_contact_id: str = ""
    status: str = ""
    skipped_reason: str = ""
    ambiguous_candidates: list[str] = field(default_factory=list)
    error: str = ""


def run_company(bx: Any, *, company_id: str, dry_run: bool = True) -> dict[str, Any]:
    outcome = _run_company_outcome(bx, company_id=str(company_id), dry_run=dry_run)
    return _summary([outcome], dry_run=dry_run)


def run(bx: Any, *, dry_run: bool = True, limit: int | None = None) -> dict[str, Any]:
    deals = bx.list_deals_by_stages(
        category_id=int(TELEMARKETING_CATEGORY_ID),
        stage_ids=list(TELEMARKETING_OPEN_STAGES),
        closed="N",
        select=["ID", "COMPANY_ID"],
    )
    company_ids = []
    seen = set()
    for deal in deals:
        company_id = str(deal.get("COMPANY_ID") or "")
        if not company_id or company_id in seen:
            continue
        seen.add(company_id)
        company_ids.append(company_id)
    if limit:
        company_ids = company_ids[:limit]
    outcomes = [_run_company_outcome(bx, company_id=company_id, dry_run=dry_run) for company_id in company_ids]
    return _summary(outcomes, dry_run=dry_run)


def _run_company_outcome(bx: Any, *, company_id: str, dry_run: bool) -> DirectorInnOutcome:
    try:
        requisites = bx.list_company_requisites(company_id)
        if any(_clean(req.get("RQ_OGRNIP")) for req in requisites):
            return _outcome(company_id, "SKIPPED", skipped_reason="company_is_ip")

        inn = next((_clean(req.get("RQ_INN")) for req in requisites if _clean(req.get("RQ_INN"))), "")
        if not inn:
            return _outcome(company_id, "SKIPPED", skipped_reason="company_has_no_inn")

        html = _fetch_rusprofile_html(inn)
        if not html:
            return _outcome(company_id, "SKIPPED", skipped_reason="rusprofile_not_available")

        director = parse_director_from_rusprofile_html(html)
        if not director or not director.inn:
            return _outcome(company_id, "SKIPPED", skipped_reason="director_inn_not_found_in_rusprofile")

        contacts = bx.list_company_contacts_full(company_id)
        if not contacts:
            return _outcome(
                company_id,
                "SKIPPED",
                skipped_reason="no_company_contacts",
                director_inn=director.inn,
                director_full_name=director.full_name,
            )

        director_contacts = [contact for contact in contacts if _is_director_post(contact)]
        matched = [contact for contact in director_contacts if _fuzzy_match_name(contact, director.full_name)]
        if not matched:
            matched = [contact for contact in contacts if _fuzzy_match_name(contact, director.full_name)]

        if not matched:
            outcome = _outcome(
                company_id,
                "UNRESOLVED",
                skipped_reason="no_matching_contact",
                director_inn=director.inn,
                director_full_name=director.full_name,
            )
            if not dry_run:
                _append_audit_row(outcome)
            return outcome

        if len(matched) > 1:
            outcome = _outcome(
                company_id,
                "UNRESOLVED",
                skipped_reason="ambiguous_matches",
                ambiguous_candidates=[str(contact.get("ID") or "") for contact in matched],
                director_inn=director.inn,
                director_full_name=director.full_name,
            )
            if not dry_run:
                _append_audit_row(outcome)
            return outcome

        contact = matched[0]
        contact_id = str(contact.get("ID") or "")
        current_inn = _clean(contact.get(CONTACT_PERSONAL_INN_FIELD))
        if current_inn and current_inn != director.inn:
            outcome = _outcome(
                company_id,
                "UNRESOLVED",
                skipped_reason="manual_inn_differs",
                matched_contact_id=contact_id,
                director_inn=director.inn,
                director_full_name=director.full_name,
            )
            if not dry_run:
                _append_audit_row(outcome)
            return outcome
        if current_inn == director.inn:
            return _outcome(
                company_id,
                "SKIPPED",
                skipped_reason="already_set",
                matched_contact_id=contact_id,
                director_inn=director.inn,
                director_full_name=director.full_name,
            )

        if dry_run:
            return _outcome(
                company_id,
                "DRY_RUN",
                matched_contact_id=contact_id,
                director_inn=director.inn,
                director_full_name=director.full_name,
            )

        bx.update_contact(
            contact_id,
            {CONTACT_PERSONAL_INN_FIELD: director.inn},
            params={"REGISTER_SONET_EVENT": "Y"},
        )
        bx.add_timeline_comment(
            owner_type_id=CONTACT_OWNER_TYPE_ID,
            owner_id=contact_id,
            text=(
                f"[director-inn] ИНН физлица {director.inn} добавлен "
                f"автоматически из rusprofile (ФИО: {director.full_name})"
            ),
        )
        outcome = _outcome(
            company_id,
            "ENRICHED",
            matched_contact_id=contact_id,
            director_inn=director.inn,
            director_full_name=director.full_name,
        )
        _append_audit_row(outcome)
        return outcome
    except Exception as exc:  # noqa: BLE001
        return _outcome(company_id, "FAILED", error=str(exc)[:200])


def _is_director_post(contact: dict[str, Any]) -> bool:
    post = f"{contact.get('POST') or ''} {contact.get('TITLE') or ''}".lower()
    return any(
        keyword in post
        for keyword in ("директор", "руководитель", "гендиректор", "управляющий", "ceo", "general", "founder")
    )


def _fuzzy_match_name(contact: dict[str, Any], director_full_name: str) -> bool:
    director_parts = _normalize_full_name(director_full_name).lower().split()
    if not director_parts:
        return False
    director_surname = director_parts[0]
    director_first = director_parts[1] if len(director_parts) > 1 else ""
    director_middle = director_parts[2] if len(director_parts) > 2 else ""

    contact_last = _normalize_full_name(contact.get("LAST_NAME") or "").lower()
    contact_first = _normalize_full_name(contact.get("NAME") or "").lower()
    contact_middle = _normalize_full_name(contact.get("SECOND_NAME") or "").lower()
    if contact_last != director_surname:
        return False
    return bool(
        (contact_first and director_first and contact_first == director_first)
        or (contact_middle and director_middle and contact_middle == director_middle)
    )


def _outcome(
    company_id: str,
    status: str,
    *,
    director_inn: str = "",
    director_full_name: str = "",
    matched_contact_id: str = "",
    skipped_reason: str = "",
    ambiguous_candidates: list[str] | None = None,
    error: str = "",
) -> DirectorInnOutcome:
    return DirectorInnOutcome(
        company_id=str(company_id),
        director_inn=director_inn,
        director_full_name=director_full_name,
        matched_contact_id=matched_contact_id,
        status=status,
        skipped_reason=skipped_reason,
        ambiguous_candidates=ambiguous_candidates or [],
        error=error,
    )


def _summary(outcomes: list[DirectorInnOutcome], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "total": len(outcomes),
        "enriched": sum(1 for outcome in outcomes if outcome.status == "ENRICHED"),
        "dry_run_enrichments": sum(1 for outcome in outcomes if outcome.status == "DRY_RUN"),
        "skipped": sum(1 for outcome in outcomes if outcome.status == "SKIPPED"),
        "unresolved": sum(1 for outcome in outcomes if outcome.status == "UNRESOLVED"),
        "failed": sum(1 for outcome in outcomes if outcome.status == "FAILED"),
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }


def _append_audit_row(outcome: DirectorInnOutcome) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "enrich_director_inn.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(CSV_HEADERS)
        writer.writerow([
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            outcome.company_id,
            outcome.director_inn,
            outcome.director_full_name,
            outcome.matched_contact_id,
            outcome.status,
            outcome.skipped_reason,
        ])


def _clean(value: Any) -> str:
    return str(value or "").strip()
