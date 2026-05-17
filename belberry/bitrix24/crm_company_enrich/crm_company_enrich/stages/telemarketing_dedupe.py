"""Объединение дублей сделок в воронке телемаркетинга."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    HOLD_MARKER_DESC_FIELD,
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    HOLD_REASON_DUPLICATE,
    HOLD_REASON_FIELD,
    LOG_DIR,
    PORTAL_DOMAIN,
    SERVICE_ACCOUNT_JSON,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_DEDUPE_SHEET_ID,
    TELEMARKETING_DEDUPE_TAB_GID,
    TELEMARKETING_OPEN_STAGES,
    TELEMARKETING_STAGE_SORT,
)
from ..sheets_client import SheetsClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
APOLOGY_STAGE_ID = "C50:APOLOGY"
DEAL_OWNER_TYPE_ID = 2
DEDUPE_FALLBACK_TAB = "telemarketing_dup_unresolved"
UNRESOLVED_HEADERS = [
    "timestamp",
    "company_id",
    "company_title",
    "winner_deal_id",
    "loser_deal_ids",
    "assignee_winner",
    "active_assignee_used",
    "activity_counts_json",
    "fail_reason",
    "bitrix_link",
]
CSV_HEADERS = [
    "timestamp",
    "company_id",
    "winner_deal_id",
    "closed_deal_ids",
    "winner_assigned_by",
    "reassigned_winner_from",
    "reassigned_winner_to",
]
HARDCODED_ACTIVE_USER_IDS = {str(user_id) for user_id, _ in TELEMARKETING_ASSIGNEES}


@dataclass
class DedupeOutcome:
    company_id: str
    winner_deal_id: str = ""
    winner_assigned_by: str = ""
    closed_deal_ids: list[str] = field(default_factory=list)
    reassigned_winner_from: str = ""
    reassigned_winner_to: str = ""
    status: str = ""
    fail_reason: str = ""
    activity_counts: dict[str, int] = field(default_factory=dict)


def run(
    bx: BitrixClient,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    rotation_index: int = 0,
) -> dict:
    deals = bx.list_deals_by_stages(
        category_id=int(TELEMARKETING_CATEGORY_ID),
        stage_ids=list(TELEMARKETING_OPEN_STAGES),
        closed="N",
        select=[
            "ID",
            "TITLE",
            "COMPANY_ID",
            "CATEGORY_ID",
            "STAGE_ID",
            "CLOSED",
            "ASSIGNED_BY_ID",
            "DATE_MODIFY",
            HOLD_REASON_FIELD,
            HOLD_MARKER_FLAG_FIELD,
        ],
    )
    groups = _duplicate_groups(deals)
    if limit:
        groups = groups[:limit]

    active_user_ids = _active_user_ids(bx)
    companies_by_id = _prefetch_companies(bx, [company_id for company_id, _ in groups])
    outcomes: list[DedupeOutcome] = []
    sheet_tab = ""

    for company_id, company_deals in groups:
        outcome = _process_group(
            bx,
            company_id=company_id,
            deals=company_deals,
            active_user_ids=active_user_ids,
            rotation_index=rotation_index,
            dry_run=dry_run,
            company=companies_by_id.get(company_id),
        )
        outcomes.append(outcome)
        if outcome.status == "UNRESOLVED" and not dry_run:
            try:
                sheet_tab = _append_unresolved(outcome, company=companies_by_id.get(company_id))
            except Exception as exc:  # noqa: BLE001
                print(f"[telemarketing-dedupe] sheets_append_failed for company {outcome.company_id}: {exc}")
                _append_unresolved_csv_fallback(outcome, exc)
                outcome.fail_reason = (
                    (outcome.fail_reason or "merge_failed")
                    + f"; sheets_append_failed: {str(exc)[:120]}"
                )

    summary = _summary(outcomes, dry_run=dry_run)
    summary["sheet_tab"] = sheet_tab
    summary["outcomes"] = [outcome.__dict__ for outcome in outcomes]
    return summary


def _duplicate_groups(deals: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for deal in deals:
        if str(deal.get("STAGE_ID") or "") not in TELEMARKETING_OPEN_STAGES:
            continue
        if _marker_already_set(deal.get(HOLD_MARKER_FLAG_FIELD)):
            continue
        company_id = str(deal.get("COMPANY_ID") or "")
        if not company_id or company_id == "0":
            continue
        grouped[company_id].append(deal)
    return [
        (company_id, items)
        for company_id, items in sorted(grouped.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0])
        if len(items) >= 2
    ]


def _process_group(
    bx: BitrixClient,
    *,
    company_id: str,
    deals: list[dict[str, Any]],
    active_user_ids: set[str],
    rotation_index: int,
    dry_run: bool,
    company: dict | None,
) -> DedupeOutcome:
    activity_counts = _activity_counts(bx, deals)
    winner = _pick_winner(deals, activity_counts)
    winner_id = str(winner.get("ID") or "")
    loser_ids = [str(deal.get("ID") or "") for deal in deals if str(deal.get("ID") or "") != winner_id]
    current_assignee = str(winner.get("ASSIGNED_BY_ID") or "").strip()

    if not loser_ids:
        return DedupeOutcome(company_id, winner_id, current_assignee, status="NO_DUPLICATES", activity_counts=activity_counts)

    assignee_resolution = _resolve_winner_assignee(winner, active_user_ids, rotation_index)
    if not assignee_resolution:
        outcome = DedupeOutcome(
            company_id,
            winner_id,
            current_assignee,
            status="UNRESOLVED",
            fail_reason="cannot_determine_active_users",
            activity_counts=activity_counts,
        )
        outcome.closed_deal_ids = loser_ids
        return outcome
    winner_assignee = assignee_resolution

    outcome = DedupeOutcome(
        company_id=company_id,
        winner_deal_id=winner_id,
        winner_assigned_by=winner_assignee,
        closed_deal_ids=loser_ids,
        reassigned_winner_from=current_assignee if current_assignee != winner_assignee else "",
        reassigned_winner_to=winner_assignee if current_assignee != winner_assignee else "",
        status="DRY_RUN" if dry_run else "",
        activity_counts=activity_counts,
    )
    if dry_run:
        return outcome

    try:
        _merge_group_live(bx, winner=winner, losers=[d for d in deals if str(d.get("ID") or "") in loser_ids], winner_assignee=winner_assignee)
        outcome.status = "MERGED"
        _append_audit_row(outcome)
    except Exception as exc:  # noqa: BLE001
        outcome.status = "UNRESOLVED"
        outcome.fail_reason = str(exc)[:500]
    return outcome


def _pick_winner(deals: list[dict], activity_counts: dict[str, int]) -> dict:
    def key(deal: dict) -> tuple[int, int, float, int]:
        deal_id = str(deal.get("ID") or "")
        return (
            activity_counts.get(deal_id, 0),
            TELEMARKETING_STAGE_SORT.get(str(deal.get("STAGE_ID") or ""), 0),
            _to_timestamp(deal.get("DATE_MODIFY")),
            int(deal_id or 0),
        )

    return max(deals, key=key)


def _marker_already_set(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {"1", "Y", "TRUE"}


def _resolve_winner_assignee(winner: dict, active_user_ids: set[str], rotation_index: int) -> str:
    current = str(winner.get("ASSIGNED_BY_ID") or "").strip()
    fallback_active = HARDCODED_ACTIVE_USER_IDS
    effective_active = active_user_ids or fallback_active
    if current and current in effective_active:
        return current
    if not effective_active:
        return ""
    return _telemarketing_assignee_by_rotation(rotation_index)


def _telemarketing_assignee_by_rotation(rotation_index: int) -> str:
    assignee_ids = [str(item[0]) for item in TELEMARKETING_ASSIGNEES]
    if not assignee_ids:
        return ""
    return assignee_ids[rotation_index % len(assignee_ids)]


def _merge_group_live(
    bx: BitrixClient,
    *,
    winner: dict,
    losers: list[dict],
    winner_assignee: str,
) -> None:
    winner_id = str(winner.get("ID") or "")
    company_id = str(winner.get("COMPANY_ID") or "")
    current_assignee = str(winner.get("ASSIGNED_BY_ID") or "").strip()
    if current_assignee != winner_assignee:
        bx.update_deal(winner_id, {"ASSIGNED_BY_ID": winner_assignee})

    _transfer_unique_contacts(bx, winner_id, [str(loser.get("ID") or "") for loser in losers])
    loser_ids: list[str] = []
    for loser in losers:
        loser_id = str(loser.get("ID") or "")
        loser_ids.append(loser_id)
        bx.update_deal(
            loser_id,
            {
                "STAGE_ID": APOLOGY_STAGE_ID,
                "CLOSED": "Y",
                HOLD_REASON_FIELD: HOLD_REASON_DUPLICATE,
                HOLD_REASON_COMMENT_FIELD: f"auto-dedupe: дубль сделки {winner_id} по компании {company_id}",
                HOLD_MARKER_FLAG_FIELD: "1",
                HOLD_MARKER_DESC_FIELD: f"telemarketing-dedupe @ {datetime.now(MOSCOW_TZ).date().isoformat()}",
            },
            params={"REGISTER_SONET_EVENT": "Y"},
        )
        bx.add_timeline_comment(
            owner_type_id=DEAL_OWNER_TYPE_ID,
            owner_id=loser_id,
            text=f"[dedupe] объединено с deal #{winner_id} (winner)",
        )
    bx.add_timeline_comment(
        owner_type_id=DEAL_OWNER_TYPE_ID,
        owner_id=winner_id,
        text=f"[dedupe] поглощены дубли: {','.join(loser_ids)}",
    )


def _transfer_unique_contacts(bx: BitrixClient, winner_id: str, loser_ids: list[str]) -> None:
    winner_contacts = _contact_ids(bx.list_deal_contacts(winner_id))
    for loser_id in loser_ids:
        for contact_id in _contact_ids(bx.list_deal_contacts(loser_id)):
            if contact_id in winner_contacts:
                continue
            if bx.add_deal_contact(winner_id, contact_id):
                winner_contacts.add(contact_id)


def _contact_ids(items: list[dict]) -> set[str]:
    out: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        contact_id = str(item.get("CONTACT_ID") or item.get("ID") or "").strip()
        if contact_id:
            out.add(contact_id)
    return out


def _activity_counts(bx: BitrixClient, deals: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for deal in deals:
        deal_id = str(deal.get("ID") or "")
        counts[deal_id] = len(bx.list_deal_activities(deal_id))
    return counts


def _active_user_ids(bx: BitrixClient) -> set[str]:
    try:
        return bx.list_active_users()
    except Exception:  # noqa: BLE001
        return set()


def _prefetch_companies(bx: BitrixClient, company_ids: list[str]) -> dict[str, dict | None]:
    unique_ids = sorted(set(company_ids), key=lambda x: int(x) if x.isdigit() else x)
    if not unique_ids:
        return {}
    if not hasattr(bx, "batch"):
        return {company_id: bx.get_company(company_id) for company_id in unique_ids}

    out: dict[str, dict | None] = {}
    for off in range(0, len(unique_ids), 50):
        chunk = unique_ids[off : off + 50]
        commands = {f"co_{company_id}": ("crm.company.get", {"id": company_id}) for company_id in chunk}
        try:
            result = bx.batch(commands)
        except Exception:  # noqa: BLE001
            for company_id in chunk:
                out[company_id] = bx.get_company(company_id)
            continue
        for company_id in chunk:
            company = result.get(f"co_{company_id}")
            out[company_id] = company if isinstance(company, dict) else None
    return out


def _append_unresolved(outcome: DedupeOutcome, *, company: dict | None) -> str:
    sheets = _sheets()
    tab = _dedupe_sheet_title(sheets)
    sheets.ensure_sheet(tab)
    existing = sheets.read(tab, "A1:J1")
    if not existing:
        sheets.update(tab, "A1:J1", [UNRESOLVED_HEADERS])
    company_title = str((company or {}).get("TITLE") or f"company #{outcome.company_id}")
    sheets.append(
        tab,
        [[
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            outcome.company_id,
            company_title,
            outcome.winner_deal_id,
            ",".join(outcome.closed_deal_ids),
            outcome.reassigned_winner_from or outcome.winner_assigned_by,
            outcome.reassigned_winner_to or outcome.winner_assigned_by,
            json.dumps(outcome.activity_counts, ensure_ascii=False, sort_keys=True),
            outcome.fail_reason,
            f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/company/details/{outcome.company_id}/";"{company_title}")',
        ]],
        value_input_option="USER_ENTERED",
    )
    return tab


def _append_unresolved_csv_fallback(outcome: DedupeOutcome, exc: Exception) -> None:
    """Локальный CSV-fallback, когда Sheets недоступен."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "telemarketing_dedupe_failed.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow([
                "timestamp",
                "company_id",
                "winner_deal_id",
                "closed_deal_ids",
                "fail_reason",
                "sheets_error",
            ])
        writer.writerow([
            datetime.now(MOSCOW_TZ).isoformat(),
            outcome.company_id,
            outcome.winner_deal_id,
            ",".join(outcome.closed_deal_ids),
            outcome.fail_reason,
            str(exc)[:200],
        ])


def _dedupe_sheet_title(sheets: SheetsClient) -> str:
    title = ""
    if hasattr(sheets, "get_sheet_title_by_id"):
        title = sheets.get_sheet_title_by_id(TELEMARKETING_DEDUPE_TAB_GID) or ""
    return title or DEDUPE_FALLBACK_TAB


def _sheets() -> SheetsClient:
    return SheetsClient(
        sheet_id=TELEMARKETING_DEDUPE_SHEET_ID,
        service_account_path=SERVICE_ACCOUNT_JSON,
    )


def _append_audit_row(outcome: DedupeOutcome) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "telemarketing_dedupe.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                "company_id": outcome.company_id,
                "winner_deal_id": outcome.winner_deal_id,
                "closed_deal_ids": ",".join(outcome.closed_deal_ids),
                "winner_assigned_by": outcome.winner_assigned_by,
                "reassigned_winner_from": outcome.reassigned_winner_from,
                "reassigned_winner_to": outcome.reassigned_winner_to,
            }
        )


def _summary(outcomes: list[DedupeOutcome], *, dry_run: bool) -> dict[str, Any]:
    merged = sum(1 for outcome in outcomes if outcome.status == "MERGED")
    dry_run_count = sum(1 for outcome in outcomes if outcome.status == "DRY_RUN")
    unresolved = sum(1 for outcome in outcomes if outcome.status == "UNRESOLVED")
    no_duplicates = sum(1 for outcome in outcomes if outcome.status == "NO_DUPLICATES")
    loser_count = sum(len(outcome.closed_deal_ids) for outcome in outcomes if outcome.status in {"MERGED", "DRY_RUN"})
    reassignments = sum(1 for outcome in outcomes if outcome.reassigned_winner_to)
    return {
        "dry_run": dry_run,
        "duplicate_companies": len(outcomes),
        "merged": merged,
        "dry_run_merged": dry_run_count,
        "loser_count": loser_count,
        "reassignments": reassignments,
        "unresolved": unresolved,
        "no_duplicates": no_duplicates,
    }


def _to_timestamp(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0.0
