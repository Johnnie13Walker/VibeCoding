"""Scoped dedupe контактов компании."""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    CONTACT_DEDUPE_MIN_SIGNALS,
    CONTACT_DEDUPE_SHEET_TAB,
    CONTACT_DEDUPE_SKIP_MULTI_COMPANY,
    LOG_DIR,
    PORTAL_DOMAIN,
    SERVICE_ACCOUNT_JSON,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_OPEN_STAGES,
    TELEMARKETING_DEDUPE_SHEET_ID,
)
from ..sheets_client import SheetsClient
from .sync_deals import _missing_deal_contacts

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
_default_workspace = Path(__file__).resolve().parents[5] if (Path(__file__).resolve().parents[5] / "belberry/bitrix24").exists() else Path("/Users/pro2kuror/Desktop/VibeCoding")
BACKUP_DIR = Path(os.environ.get("CCE_CONTACT_DEDUPE_BACKUP_DIR", str(_default_workspace / "belberry/bitrix24/backups")))

UNRESOLVED_HEADERS = [
    "timestamp",
    "company_id",
    "contact_ids",
    "winner_contact_id",
    "reason",
    "match_reasons",
    "bitrix_link",
]


@dataclass
class ContactDedupeOutcome:
    company_id: str
    winner_contact_id: str = ""
    closed_contact_ids: list[str] = field(default_factory=list)
    deals_updated: list[str] = field(default_factory=list)
    deals_with_added_contacts: dict[str, list[str]] = field(default_factory=dict)
    status: str = ""
    skipped_reason: str = ""
    fail_reason: str = ""


def run_company(bx: BitrixClient, *, company_id: str, dry_run: bool = True) -> dict:
    """Scoped dedupe контактов одной компании + re-attach в открытые сделки C50."""
    company_id = str(company_id)
    contacts = bx.list_company_contacts_full(company_id)
    outcomes: list[ContactDedupeOutcome] = []

    if len(contacts) >= 2:
        clusters = [cluster for cluster in _cluster_duplicates(contacts) if len(cluster) >= 2]
        for cluster in clusters:
            outcome = _process_cluster(bx, company_id, cluster, dry_run=dry_run)
            outcomes.append(outcome)
            _record_unresolved_if_needed(outcome, cluster=cluster, dry_run=dry_run)

    deal_updates = _attach_missing_contacts_to_open_deals(bx, company_id, dry_run=dry_run)
    if not outcomes:
        status = "NO_DUPLICATES"
        if len(contacts) < 2:
            status = "NO_DUPLICATES"
        outcomes.append(
            ContactDedupeOutcome(
                company_id=company_id,
                status=status,
                skipped_reason="not_enough_contacts" if len(contacts) < 2 else "",
                deals_with_added_contacts=deal_updates,
                deals_updated=sorted(deal_updates),
            )
        )
    else:
        for outcome in outcomes:
            outcome.deals_with_added_contacts.update(deal_updates)
            outcome.deals_updated = sorted(set(outcome.deals_updated) | set(deal_updates))

    return _summary(company_id, outcomes, dry_run=dry_run)


def _process_cluster(
    bx: BitrixClient,
    company_id: str,
    cluster: list[dict],
    *,
    dry_run: bool,
) -> ContactDedupeOutcome:
    contact_deals = {str(c.get("ID")): bx.list_contact_deals(str(c.get("ID"))) for c in cluster}
    winner = _pick_winner(cluster, contact_deals)
    winner_id = str(winner.get("ID") or "")
    losers = [c for c in cluster if str(c.get("ID") or "") != winner_id]
    unresolved_reason = _unresolved_reason(bx, cluster)
    if unresolved_reason:
        return ContactDedupeOutcome(
            company_id=company_id,
            winner_contact_id=winner_id,
            status="UNRESOLVED",
            skipped_reason=unresolved_reason,
            fail_reason=unresolved_reason,
        )

    if dry_run:
        return ContactDedupeOutcome(
            company_id=company_id,
            winner_contact_id=winner_id,
            closed_contact_ids=[str(c.get("ID") or "") for c in losers],
            status="DRY_RUN",
        )

    outcome = ContactDedupeOutcome(company_id=company_id, winner_contact_id=winner_id, status="MERGED")
    try:
        for loser in losers:
            loser_id = str(loser.get("ID") or "")
            _merge_contact_into_winner(
                bx,
                winner=winner,
                loser=loser,
                company_id=company_id,
                loser_deals=contact_deals.get(loser_id, []),
                dry_run=False,
            )
            outcome.closed_contact_ids.append(loser_id)
        outcome.deals_updated = sorted({
            str(deal.get("ID") or "")
            for loser_id in outcome.closed_contact_ids
            for deal in contact_deals.get(loser_id, [])
            if deal.get("ID")
        })
    except Exception as exc:  # noqa: BLE001
        outcome.status = "FAILED"
        outcome.fail_reason = str(exc)[:300]
    return outcome


def _merge_contact_into_winner(
    bx: BitrixClient,
    *,
    winner: dict,
    loser: dict,
    company_id: str,
    loser_deals: list[dict],
    dry_run: bool,
) -> dict[str, Any]:
    winner_id = str(winner.get("ID") or "")
    loser_id = str(loser.get("ID") or "")
    fields = _merged_contact_fields(winner, loser)
    plan = {
        "winner_contact_id": winner_id,
        "loser_contact_id": loser_id,
        "fields": fields,
        "deal_ids": [str(deal.get("ID")) for deal in loser_deals if deal.get("ID")],
        "company_id": company_id,
    }
    if dry_run:
        return plan

    _backup_contact(loser, plan=plan)
    if fields:
        bx.update_contact(winner_id, fields)
    for deal in loser_deals:
        deal_id = str(deal.get("ID") or "")
        if not deal_id:
            continue
        linked = {
            str(item.get("CONTACT_ID") or item.get("ID") or "")
            for item in bx.list_deal_contacts(deal_id)
            if isinstance(item, dict)
        }
        if winner_id not in linked:
            bx.add_deal_contact(deal_id, winner_id)
        bx.remove_deal_contact_relation(deal_id, loser_id)
    bx.remove_contact_company_relation(loser_id, company_id)
    bx.delete_contact(loser_id)
    return plan


def _attach_missing_contacts_to_open_deals(
    bx: BitrixClient,
    company_id: str,
    *,
    dry_run: bool,
) -> dict[str, list[str]]:
    updates: dict[str, list[str]] = {}
    for deal in bx.list_company_deals(company_id):
        deal_id = str(deal.get("ID") or "")
        if not deal_id:
            continue
        if str(deal.get("CATEGORY_ID") or "") != str(TELEMARKETING_CATEGORY_ID):
            continue
        if str(deal.get("STAGE_ID") or "") not in TELEMARKETING_OPEN_STAGES:
            continue
        if str(deal.get("CLOSED") or "").upper() == "Y":
            continue
        contacts_to_add, _ = _missing_deal_contacts(bx, company_id, deal_id)
        if not contacts_to_add:
            continue
        updates[deal_id] = contacts_to_add
        if dry_run:
            continue
        for contact_id in contacts_to_add:
            bx.add_deal_contact(deal_id, contact_id)
    return updates


def _cluster_duplicates(contacts: list[dict]) -> list[list[dict]]:
    parent = {str(c.get("ID") or ""): str(c.get("ID") or "") for c in contacts if c.get("ID")}
    signals = {str(c.get("ID") or ""): _strong_signals(c) for c in contacts if c.get("ID")}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    ids = list(parent)
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            score, reasons = _match_score(signals[a_id], signals[b_id])
            if score >= CONTACT_DEDUPE_MIN_SIGNALS or (score == 1 and set(reasons) & {"phone", "email"}):
                union(a_id, b_id)

    by_id = {str(c.get("ID") or ""): c for c in contacts if c.get("ID")}
    grouped: dict[str, list[dict]] = {}
    for contact_id in ids:
        grouped.setdefault(find(contact_id), []).append(by_id[contact_id])
    return list(grouped.values())


def _normalize_name(c: dict) -> str:
    parts = [_clean(c.get(k)) for k in ("LAST_NAME", "NAME", "SECOND_NAME")]
    joined = " ".join(p for p in parts if p).lower().strip()
    return re.sub(r"\s+", " ", joined).replace("-", "")


def _normalize_phones(c: dict) -> set[str]:
    out: set[str] = set()
    for item in c.get("PHONE") or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        digits = re.sub(r"\D+", "", _clean(value))
        if len(digits) >= 10:
            out.add(digits[-10:])
    return out


def _normalize_emails(c: dict) -> set[str]:
    out: set[str] = set()
    for item in c.get("EMAIL") or []:
        value = _clean(item.get("VALUE") if isinstance(item, dict) else item).lower()
        if "@" in value:
            out.add(value)
    return out


def _strong_signals(c: dict) -> dict:
    return {
        "name": _normalize_name(c),
        "phones": _normalize_phones(c),
        "emails": _normalize_emails(c),
    }


def _match_score(a: dict, b: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if a["name"] and a["name"] == b["name"]:
        score += 1
        reasons.append("name")
    if a["phones"] & b["phones"]:
        score += 1
        reasons.append("phone")
    if a["emails"] & b["emails"]:
        score += 1
        reasons.append("email")
    return score, reasons


def _pick_winner(cluster: list[dict], contact_deals: dict[str, list[dict]]) -> dict:
    def key(contact: dict) -> tuple[int, int, float, int]:
        contact_id = str(contact.get("ID") or "")
        return (
            _filled_score(contact),
            len(contact_deals.get(contact_id, [])),
            -_to_timestamp(contact.get("DATE_CREATE")),
            -int(contact_id) if contact_id.isdigit() else 0,
        )
    return max(cluster, key=key)


def _filled_score(contact: dict) -> int:
    score = 0
    for key in ("LAST_NAME", "NAME", "SECOND_NAME", "POST", "TITLE"):
        if _clean(contact.get(key)):
            score += 1
    score += len(_normalize_phones(contact))
    score += len(_normalize_emails(contact))
    score += sum(1 for key, value in contact.items() if str(key).startswith("UF_") and _clean(value))
    return score


def _unresolved_reason(bx: BitrixClient, cluster: list[dict]) -> str:
    if _max_match_score(cluster) < CONTACT_DEDUPE_MIN_SIGNALS:
        return "weak_match"
    if CONTACT_DEDUPE_SKIP_MULTI_COMPANY:
        for contact in cluster:
            contact_id = str(contact.get("ID") or "")
            companies = set(bx.list_contact_companies(contact_id))
            if len(companies) > 1:
                return f"multi_company_contact:{contact_id}"
    titles = {_clean(c.get("POST") or c.get("TITLE")) for c in cluster if _clean(c.get("POST") or c.get("TITLE"))}
    if len(titles) > 1:
        return "conflicting_title"
    return ""


def _max_match_score(cluster: list[dict]) -> int:
    max_score = 0
    signals = [_strong_signals(c) for c in cluster]
    for i, a in enumerate(signals):
        for b in signals[i + 1:]:
            score, _ = _match_score(a, b)
            max_score = max(max_score, score)
    return max_score


def _merged_contact_fields(winner: dict, loser: dict) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    phones = _merge_multifield(winner.get("PHONE"), loser.get("PHONE"), normalizer=_phone_key)
    emails = _merge_multifield(winner.get("EMAIL"), loser.get("EMAIL"), normalizer=_email_key)
    if phones != (winner.get("PHONE") or []):
        fields["PHONE"] = phones
    if emails != (winner.get("EMAIL") or []):
        fields["EMAIL"] = emails
    return fields


def _merge_multifield(current: Any, extra: Any, *, normalizer) -> list[dict]:
    result = [dict(item) for item in (current or []) if isinstance(item, dict)]
    seen = {normalizer(item) for item in result if normalizer(item)}
    for item in extra or []:
        if not isinstance(item, dict):
            continue
        key = normalizer(item)
        if not key or key in seen:
            continue
        result.append(dict(item))
        seen.add(key)
    return result


def _phone_key(item: dict) -> str:
    digits = re.sub(r"\D+", "", _clean(item.get("VALUE")))
    return digits[-10:] if len(digits) >= 10 else ""


def _email_key(item: dict) -> str:
    value = _clean(item.get("VALUE")).lower()
    return value if "@" in value else ""


def _backup_contact(contact: dict, *, plan: dict[str, Any]) -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    contact_id = str(contact.get("ID") or "unknown")
    path = BACKUP_DIR / f"dedupe_contact_{contact_id}_{ts}.json"
    payload = {
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "contact": contact,
        "plan": plan,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path)


def _record_unresolved_if_needed(outcome: ContactDedupeOutcome, *, cluster: list[dict], dry_run: bool) -> None:
    if dry_run or outcome.status != "UNRESOLVED":
        return
    try:
        _append_unresolved(outcome, cluster=cluster)
    except Exception as exc:  # noqa: BLE001
        _append_unresolved_csv_fallback(outcome, cluster=cluster, exc=exc)
        outcome.fail_reason = (
            (outcome.fail_reason or outcome.skipped_reason or "unresolved")
            + f"; sheets_append_failed: {str(exc)[:120]}"
        )


def _append_unresolved(outcome: ContactDedupeOutcome, *, cluster: list[dict]) -> str:
    sheets = _sheets()
    sheets.ensure_sheet(CONTACT_DEDUPE_SHEET_TAB)
    existing = sheets.read(CONTACT_DEDUPE_SHEET_TAB, "A1:G1")
    if not existing:
        sheets.update(CONTACT_DEDUPE_SHEET_TAB, "A1:G1", [UNRESOLVED_HEADERS])
    contact_ids = [str(c.get("ID") or "") for c in cluster]
    match_reasons = _cluster_match_reasons(cluster)
    sheets.append(
        CONTACT_DEDUPE_SHEET_TAB,
        [[
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            outcome.company_id,
            ",".join(contact_ids),
            outcome.winner_contact_id,
            outcome.fail_reason or outcome.skipped_reason,
            ",".join(match_reasons),
            f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/company/details/{outcome.company_id}/";"company {outcome.company_id}")',
        ]],
        value_input_option="USER_ENTERED",
    )
    return CONTACT_DEDUPE_SHEET_TAB


def _append_unresolved_csv_fallback(
    outcome: ContactDedupeOutcome,
    *,
    cluster: list[dict],
    exc: Exception,
) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "contact_dedupe_unresolved_failed.csv"
    write_header = not path.exists()
    contact_ids = [str(c.get("ID") or "") for c in cluster]
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow([
                "timestamp",
                "company_id",
                "contact_ids",
                "winner_contact_id",
                "reason",
                "sheets_error",
            ])
        writer.writerow([
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            outcome.company_id,
            ",".join(contact_ids),
            outcome.winner_contact_id,
            outcome.fail_reason or outcome.skipped_reason,
            str(exc)[:200],
        ])


def _cluster_match_reasons(cluster: list[dict]) -> list[str]:
    reasons: set[str] = set()
    signals = [_strong_signals(c) for c in cluster]
    for i, a in enumerate(signals):
        for b in signals[i + 1:]:
            _, pair_reasons = _match_score(a, b)
            reasons.update(pair_reasons)
    return sorted(reasons)


def _sheets() -> SheetsClient:
    return SheetsClient(
        sheet_id=TELEMARKETING_DEDUPE_SHEET_ID,
        service_account_path=SERVICE_ACCOUNT_JSON,
    )


def _summary(company_id: str, outcomes: list[ContactDedupeOutcome], *, dry_run: bool) -> dict:
    return {
        "dry_run": dry_run,
        "company_id": company_id,
        "clusters": len([o for o in outcomes if o.status not in {"NO_DUPLICATES"}]),
        "merged": sum(1 for o in outcomes if o.status == "MERGED"),
        "dry_run_merges": sum(1 for o in outcomes if o.status == "DRY_RUN"),
        "no_duplicates": sum(1 for o in outcomes if o.status == "NO_DUPLICATES"),
        "unresolved": sum(1 for o in outcomes if o.status == "UNRESOLVED"),
        "failed": sum(1 for o in outcomes if o.status == "FAILED"),
        "contacts_closed": sum(len(o.closed_contact_ids) for o in outcomes if o.status in {"MERGED", "DRY_RUN"}),
        "deals_updated": sorted({deal_id for o in outcomes for deal_id in o.deals_updated}),
        "outcomes": [o.__dict__ for o in outcomes],
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_timestamp(value: Any) -> float:
    raw = _clean(value)
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
