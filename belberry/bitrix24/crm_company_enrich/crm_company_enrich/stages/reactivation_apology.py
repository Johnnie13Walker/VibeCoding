"""Реактивация старых APOLOGY-сделок по cooldown matrix."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import (
    HOLD_REASON_FIELD,
    LAST_AUTO_ACTION_DESC_FIELD,
    LOG_DIR,
    PORTAL_DOMAIN,
    REACTIVATION_COUNT_FIELD,
    SERVICE_ACCOUNT_JSON,
    SHEET_ID,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_NEW_STAGE_ID,
    TELEMARKETING_REVIVE_SOURCE_ID,
)
from ..sheets_client import SheetsClient
from .auto_revive_lose import _resolve_revive_assignee
from .telemarketing_dedupe import _active_user_ids

APOLOGY_STAGE_ID = "C50:APOLOGY"
DEAL_OWNER_TYPE_ID = 2
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UNRESOLVED_SHEET_TAB = "reactivation_unresolved"
CSV_HEADERS = [
    "timestamp",
    "deal_id",
    "company_id",
    "reason_id",
    "cooldown_months",
    "reactivation_count_after",
    "new_assignee",
    "status",
]

# int N: cooldown N месяцев; None: никогда; trigger_only: только по триггеру.
COOLDOWN_BY_REASON_MONTHS: dict[str, int | None | str] = {
    "8538": None,
    "8540": 12,
    "8542": None,
    "8544": None,
    "8546": 6,
    "8548": 12,
    "8550": 12,
    "8838": 6,
    "8840": "trigger_only",
    "8842": None,
}

TRIGGER_BY_REASON = {
    "8840": "contacts_appeared",
}


@dataclass
class ReactivationOutcome:
    deal_id: str
    company_id: str
    reason_id: str
    reactivation_count_before: int
    new_assignee: str
    status: str
    skipped_reason: str = ""
    error: str = ""


def run(
    bx: Any,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    today: date | None = None,
    rotation_index: int = 0,
) -> dict[str, Any]:
    today = today or datetime.now(MOSCOW_TZ).date()
    deals = _list_apology_deals(bx)
    if limit:
        deals = deals[:limit]

    active_users = _active_user_ids(bx)
    outcomes: list[ReactivationOutcome] = []
    used_rotation = 0
    for deal in deals:
        outcome, used = _process_deal(
            bx,
            deal,
            dry_run=dry_run,
            today=today,
            active_user_ids=active_users,
            rotation_index=rotation_index + used_rotation,
        )
        if used:
            used_rotation += 1
        outcomes.append(outcome)
        if not dry_run and outcome.status == "SKIPPED" and outcome.skipped_reason == "no_trigger_yet":
            _append_no_trigger_unresolved(outcome)
    return _summary(outcomes, dry_run=dry_run)


def _process_deal(
    bx: Any,
    deal: dict[str, Any],
    *,
    dry_run: bool,
    today: date,
    active_user_ids: set[str],
    rotation_index: int,
) -> tuple[ReactivationOutcome, bool]:
    deal_id = str(deal.get("ID") or "")
    company_id = str(deal.get("COMPANY_ID") or "")
    reason_id = str(deal.get(HOLD_REASON_FIELD) or "")
    count_before = _reactivation_count(deal)
    company = bx.get_company(company_id) if company_id else {}
    eligible, skipped_reason = _is_eligible(deal, company or {}, today)
    if not eligible:
        return (
            ReactivationOutcome(deal_id, company_id, reason_id, count_before, "", "SKIPPED", skipped_reason),
            False,
        )

    new_assignee, used_rotation = _resolve_revive_assignee(
        str(deal.get("ASSIGNED_BY_ID") or ""),
        active_user_ids,
        rotation_index,
    )
    if dry_run:
        return (
            ReactivationOutcome(deal_id, company_id, reason_id, count_before, new_assignee, "DRY_RUN"),
            used_rotation,
        )

    try:
        count_after = count_before + 1
        bx.update_deal(
            deal_id,
            {
                "STAGE_ID": TELEMARKETING_NEW_STAGE_ID,
                "CLOSED": "N",
                "SOURCE_ID": TELEMARKETING_REVIVE_SOURCE_ID,
                "ASSIGNED_BY_ID": new_assignee,
                REACTIVATION_COUNT_FIELD: count_after,
                LAST_AUTO_ACTION_DESC_FIELD: f"reactivation {today.isoformat()} #{count_after}",
            },
            params={"REGISTER_SONET_EVENT": "Y"},
        )
        bx.add_timeline_comment(
            owner_type_id=DEAL_OWNER_TYPE_ID,
            owner_id=deal_id,
            text=f"[reactivation] возврат из APOLOGY (reason {reason_id})",
        )
        _append_audit_row(
            ReactivationOutcome(deal_id, company_id, reason_id, count_before, new_assignee, "REACTIVATED"),
            count_after,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            ReactivationOutcome(deal_id, company_id, reason_id, count_before, new_assignee, "FAILED", error=str(exc)[:200]),
            False,
        )
    return (
        ReactivationOutcome(deal_id, company_id, reason_id, count_before, new_assignee, "REACTIVATED"),
        used_rotation,
    )


def _is_eligible(deal: dict[str, Any], company: dict[str, Any], today: date) -> tuple[bool, str]:
    reason_id = str(deal.get(HOLD_REASON_FIELD) or "")
    if reason_id not in COOLDOWN_BY_REASON_MONTHS:
        return False, "unknown_reason"
    cooldown = COOLDOWN_BY_REASON_MONTHS[reason_id]
    if cooldown is None:
        return False, "never_reactivate"
    close_date = _parse_date(deal.get("CLOSEDATE")) or _parse_date(deal.get("DATE_MODIFY"))
    if not close_date:
        return False, "missing_close_date"
    if cooldown == "trigger_only":
        if reason_id == "8840":
            if _has_new_contacts_since(company, close_date):
                return True, ""
            return False, "no_trigger_yet"
        return False, f"unknown_trigger_for_{reason_id}"

    if today < _add_months(close_date, cooldown):
        return False, "too_early"
    return True, ""


def _list_apology_deals(bx: Any) -> list[dict[str, Any]]:
    return list(
        bx.list_deals_by_stages(
            category_id=int(TELEMARKETING_CATEGORY_ID),
            stage_ids=[APOLOGY_STAGE_ID],
            closed="Y",
            select=[
                "ID",
                "TITLE",
                "STAGE_ID",
                "COMPANY_ID",
                "ASSIGNED_BY_ID",
                "CLOSED",
                "CLOSEDATE",
                "DATE_MODIFY",
                HOLD_REASON_FIELD,
                REACTIVATION_COUNT_FIELD,
            ],
        )
    )


def _has_phone_or_email(company: dict[str, Any]) -> bool:
    return _has_multifield(company, "PHONE") or _has_multifield(company, "EMAIL")


def _has_new_contacts_since(company: dict[str, Any], since_date: date) -> bool:
    """Proxy-baseline для 8840.

    Bitrix multi-fields не дают created_at по конкретному телефону/email.
    Поэтому считаем триггером только наличие phone/email при DATE_MODIFY
    компании позже даты закрытия сделки. Это не идеальный baseline:
    DATE_MODIFY меняется при любом edit карточки, но снижает false-positive
    относительно прежнего правила "любой phone/email".
    """
    modified = _parse_date(company.get("DATE_MODIFY"))
    if not modified or modified <= since_date:
        return False
    return _has_phone_or_email(company)


def _has_multifield(entity: dict[str, Any], field: str) -> bool:
    for item in entity.get(field) or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        if str(value or "").strip():
            return True
    return False


def _reactivation_count(deal: dict[str, Any]) -> int:
    raw = deal.get(REACTIVATION_COUNT_FIELD)
    if raw in (None, "", 0, "0"):
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return value.replace(year=year, month=month, day=min(value.day, days[month - 1]))


def _summary(outcomes: list[ReactivationOutcome], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "total": len(outcomes),
        "reactivated": sum(1 for outcome in outcomes if outcome.status == "REACTIVATED"),
        "dry_run_reactivations": sum(1 for outcome in outcomes if outcome.status == "DRY_RUN"),
        "skipped": sum(1 for outcome in outcomes if outcome.status == "SKIPPED"),
        "failed": sum(1 for outcome in outcomes if outcome.status == "FAILED"),
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }


def _append_audit_row(outcome: ReactivationOutcome, count_after: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "reactivation_apology.csv"
    write_header = not path.exists()
    cooldown = COOLDOWN_BY_REASON_MONTHS.get(outcome.reason_id)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(CSV_HEADERS)
        writer.writerow(
            [
                datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                outcome.deal_id,
                outcome.company_id,
                outcome.reason_id,
                cooldown if isinstance(cooldown, int) else "",
                count_after,
                outcome.new_assignee,
                outcome.status,
            ]
        )


def _append_no_trigger_unresolved(outcome: ReactivationOutcome) -> None:
    try:
        sheets = _sheets()
        sheets.ensure_sheet(UNRESOLVED_SHEET_TAB)
        if not sheets.read(UNRESOLVED_SHEET_TAB, "A1:H1"):
            sheets.update(
                UNRESOLVED_SHEET_TAB,
                "A1:H1",
                [[
                    "timestamp",
                    "deal_id",
                    "company_id",
                    "reason_id",
                    "skipped_reason",
                    "reactivation_count_before",
                    "new_assignee",
                    "bitrix_link",
                ]],
            )
        if _unresolved_deal_already_exists(sheets, outcome.deal_id):
            return
        sheets.append(
            UNRESOLVED_SHEET_TAB,
            [[
                datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                outcome.deal_id,
                outcome.company_id,
                outcome.reason_id,
                outcome.skipped_reason,
                outcome.reactivation_count_before,
                outcome.new_assignee,
                f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/deal/details/{outcome.deal_id}/";"deal #{outcome.deal_id}")',
            ]],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[reactivation] sheets_append_failed for deal {outcome.deal_id}: {exc}")


def _unresolved_deal_already_exists(sheets: SheetsClient, deal_id: str) -> bool:
    try:
        values = sheets.read(UNRESOLVED_SHEET_TAB, "B2:B")
    except Exception:  # noqa: BLE001
        return False
    existing_ids = {
        str(row[0]).strip()
        for row in values
        if row and str(row[0]).strip()
    }
    return str(deal_id) in existing_ids


def _sheets() -> SheetsClient:
    return SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)
