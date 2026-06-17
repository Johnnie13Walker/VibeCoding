"""Pipeline для 1 273 пустых компаний Belberry/Acoola.

Стадия изолирована от company_enrich_queue и TM Phase 2:
- вход: belberry/bitrix24/data/empty_companies_to_enrich.json
- state/evidence: belberry/bitrix24/data/empty_companies_enrich_state.json
- Sheets tab: "Enrich empty — план" в отдельной таблице cleanup-а.

WRITE в Bitrix выполняется только отдельной apply-командой после checkpoint.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ..bitrix_client import BitrixClient
from ..config import (
    CCE_APPLY_SLEEP_S,
    CCE_BIZPROC_FIRST_ENTRY_ID,
    CCE_BIZPROC_UPDATE_ID,
    CCE_BIZPROC_WAIT_S,
    CCE_COMPANY_TOUCH,
    CCE_PRESET_ID,
    COMPANY_REGION_ENUM_MAP,
    COMPANY_UF_LEGAL_ADDRESS,
    COMPANY_UF_CITY,
    COMPANY_UF_REGION,
    ENTITY_TYPE_COMPANY,
    LOG_PATH,
    SERVICE_ACCOUNT_JSON,
    STATE_PATH,
    TELEMARKETING_REFUSAL_STAGE_IDS,
    UF_BRAND_FIELD,
)
from ..hyperlinks import company_link
from ..models import is_valid_inn_format, normalize_inn
from ..sheets_client import SheetsClient
from .enrich_web import extract_company_name_from_html, extract_inn_from_text

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

_default_workspace = Path(__file__).resolve().parents[5] if (Path(__file__).resolve().parents[5] / "belberry/bitrix24").exists() else Path("/Users/pro2kuror/Desktop/VibeCoding")
WORKSPACE_ROOT = Path(os.environ.get("CCE_WORKSPACE_ROOT", str(_default_workspace)))
DATA_DIR = Path(os.environ.get("CCE_DATA_DIR", str(WORKSPACE_ROOT / "belberry/bitrix24/data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
INPUT_PATH = DATA_DIR / "empty_companies_to_enrich.json"
STATE_JSON = DATA_DIR / "empty_companies_enrich_state.json"
PLAN_JSON = DATA_DIR / "empty_companies_enrich_plan.json"
SHEET_ID = os.environ.get("CCE_EMPTY_SHEET_ID", "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4")
TAB_DO_NOT_TOUCH = os.environ.get("CCE_EMPTY_DO_NOT_TOUCH_TAB", "Не трогать")
TAB_PLAN = "Enrich empty — план"
TAB_MANUAL_SITE = "Enrich empty — ручной сайт"

PLAN_HEADERS = [
    "company_id",
    "score",
    "source",
    "inn_candidate",
    "geo_verified",
    "brand_predicted",
    "brand_evidence",
    "classification",
    "evidence",
    "apply_status",
]

MANUAL_SITE_HEADERS = [
    "company",
    "score",
    "phone",
    "old_site",
    "city",
    "search_phone",
    "search_domain",
    "new_site",
    "inn",
    "brand",
    "approve",
    "note",
]

EMPTY_WEB_PATHS = ("/", "/requisites/", "/реквизиты/", "/contacts/", "/контакты/")
EMPTY_WEB_TIMEOUT_S = float(os.environ.get("CCE_EMPTY_WEB_TIMEOUT_S", "4"))
EMPTY_FALLBACK_TIMEOUT_S = float(os.environ.get("CCE_EMPTY_FALLBACK_TIMEOUT_S", "5"))
EMPTY_ENABLE_CHECKO = os.environ.get("CCE_EMPTY_ENABLE_CHECKO", "").lower() in {"1", "true", "yes", "on"}

MEDICAL_OKVED_PREFIXES = ("86", "87.10", "87.20", "87.30", "87.90", "21.20.10")
MEDICAL_KEYWORDS = (
    "клиник", "стомат", "дентал", "дент", "медицин", "медиц", "лечебн",
    "диагност", "реабилит", "лаборатори", "поликлиник", "больниц",
    "санатор", "врач", "аптек", "фарм", "ортопед", "офтальм",
    "гинеколог", "косметолог", "эстетик", "эко-центр", "репродукт",
    "невролог", "терапия", "clinic", "med", "dent", "stom", "doctor",
    "health", "pharm", "hospital",
)
DOMAIN_MEDICAL_HINTS = (
    ".clinic", "clinic", "klinika", "med", "dent", "dental", "stom",
    "doctor", "health", "pharm", "apteka", "mrt", "uzi", "rehab",
)
NON_MEDICAL_KEYWORDS = (
    "авто", "автосервис", "недвиж", "мебел", "ресторан", "кафе",
    "магазин", "ритейл", "e-commerce", "маркет", "строй", "логист",
    "юрист", "адвокат", "it", "software", "школа", "образован",
)

PHONE_CITY_HINTS = {
    "495": ("москва", "московская"),
    "499": ("москва", "московская"),
    "812": ("санкт-петербург", "петербург", "ленинградская"),
    "383": ("новосибирск",),
    "343": ("екатеринбург", "свердловская"),
    "846": ("самара",),
    "843": ("казань", "татарстан"),
    "861": ("краснодар",),
    "863": ("ростов",),
    "831": ("нижний новгород",),
}


@dataclass
class PlanRow:
    company_id: str
    title: str
    score: int
    source: str = ""
    inn_candidate: str = ""
    geo_verified: bool = False
    brand_predicted: str = ""
    brand_evidence: str = ""
    classification: str = "NO_INN_FOUND"
    evidence: dict[str, Any] = field(default_factory=dict)
    apply_status: str = ""
    duplicate_company_ids: list[str] = field(default_factory=list)
    duplicate_active_deals: list[dict[str, str]] = field(default_factory=list)
    duplicate_requisite_ids: list[str] = field(default_factory=list)
    duplicate_reason: str = ""
    duplicate_check_failed: bool = False

    def to_sheet_row(self) -> list[str]:
        return [
            company_link(self.company_id, self.title or f"company #{self.company_id}"),
            str(self.score),
            self.source,
            self.inn_candidate,
            "да" if self.geo_verified else "нет",
            self.brand_predicted,
            self.brand_evidence,
            self.classification,
            json.dumps(self.evidence, ensure_ascii=False, sort_keys=True)[:45000],
            self.apply_status,
        ]


def run_discover(*, limit: int | None = None) -> dict:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = _sheets()
    source_rows = _read_input()
    if limit:
        source_rows = source_rows[:limit]

    do_not_touch_deal_ids = _read_do_not_touch_deal_ids(sheets)
    do_not_touch = _deal_ids_to_company_ids(bx, do_not_touch_deal_ids)
    with_inn = _existing_inn_ids(bx, [str(r["id"]) for r in source_rows])

    pool = []
    skipped_do_not_touch = 0
    skipped_has_inn = 0
    for raw in source_rows:
        cid = str(raw["id"])
        if cid in do_not_touch:
            skipped_do_not_touch += 1
            continue
        if cid in with_inn:
            skipped_has_inn += 1
            continue
        pool.append(raw)

    state = {
        "ts_msk": _now(),
        "input_count": len(source_rows),
        "pool": pool,
        "skip": {
            "do_not_touch": skipped_do_not_touch,
            "already_has_inn": skipped_has_inn,
        },
        "do_not_touch_deals": sorted(do_not_touch_deal_ids, key=int),
        "do_not_touch_companies": sorted(do_not_touch, key=int),
        "results": [],
    }
    _write_json(STATE_JSON, state)
    return {
        "input": len(source_rows),
        "pool": len(pool),
        "skipped_do_not_touch": skipped_do_not_touch,
        "skipped_already_has_inn": skipped_has_inn,
        "do_not_touch_deals": len(do_not_touch_deal_ids),
        "do_not_touch_companies": len(do_not_touch),
        "state": str(STATE_JSON),
    }


def run_enrich(*, limit: int | None = None, throttle_s: float = 0.1) -> dict:
    state = _load_state()
    pool = state.get("pool") or []
    processed_ids = {str(r.get("company_id")) for r in state.get("results", [])}
    targets = [r for r in pool if str(r.get("id")) not in processed_ids]
    if limit:
        targets = targets[:limit]

    dadata = DadataClient.from_env(required=False)
    checko = CheckoClient()
    rusprofile = RusprofileClient()

    added: list[dict[str, Any]] = []
    for idx, raw in enumerate(targets, start=1):
        if idx > 1 and throttle_s > 0:
            time.sleep(throttle_s)
        row = _enrich_one(raw, dadata=dadata, checko=checko, rusprofile=rusprofile)
        added.append(row.__dict__)
        state.setdefault("results", []).append(row.__dict__)
        if idx % 5 == 0:
            _write_json(STATE_JSON, state)
            print(f"[empty-enrich] обработано {idx}/{len(targets)}")

    state["ts_msk"] = _now()
    _write_json(STATE_JSON, state)
    _write_json(PLAN_JSON, state.get("results", []))
    summary = _summary([PlanRow(**r) for r in state.get("results", [])])
    summary["added"] = len(added)
    summary["state"] = str(STATE_JSON)
    return summary


UPLOAD_PLAN_HIDDEN_STATUSES = {"APPLIED", "APPLIED_LIQUIDATED", "COMPANY_DELETED"}


def run_upload_plan() -> dict:
    state = _load_state()
    rows = [PlanRow(**r) for r in state.get("results", [])]
    visible_rows = [r for r in rows if r.apply_status not in UPLOAD_PLAN_HIDDEN_STATUSES]
    sheets = _sheets()
    sheets.ensure_sheet(TAB_PLAN)
    sheets.clear(TAB_PLAN)
    sheets.update(TAB_PLAN, "A1:J1", [PLAN_HEADERS])
    payload = [r.to_sheet_row() for r in visible_rows]
    for off in range(0, len(payload), 500):
        chunk = payload[off : off + 500]
        sheets.update(TAB_PLAN, f"A{off + 2}:J{off + len(chunk) + 1}", chunk, value_input_option="USER_ENTERED")
    summary = _summary(rows)
    summary["uploaded"] = len(payload)
    summary["hidden_applied"] = sum(1 for r in rows if r.apply_status in {"APPLIED", "APPLIED_LIQUIDATED"})
    summary["hidden_company_deleted"] = sum(1 for r in rows if r.apply_status == "COMPANY_DELETED")
    summary["sheet_tab"] = TAB_PLAN
    return summary


def run_report(*, top: int = 10) -> dict:
    rows = [PlanRow(**r) for r in _load_state().get("results", [])]
    summary = _summary(rows)
    ready = [r for r in rows if r.classification == "READY_TO_APPLY"]
    suspicious = [
        r for r in rows
        if r.classification == "MANUAL" and ("brand" in json.dumps(r.evidence, ensure_ascii=False).lower())
    ][:top]
    summary["top_ready"] = [
        {
            "company_id": r.company_id,
            "title": r.title,
            "brand": r.brand_predicted,
            "inn": r.inn_candidate,
            "source": r.source,
            "brand_evidence": r.brand_evidence,
            "evidence": r.evidence.get("decision"),
        }
        for r in ready[:top]
    ]
    summary["suspicious_manual"] = [
        {
            "company_id": r.company_id,
            "title": r.title,
            "brand": r.brand_predicted,
            "inn": r.inn_candidate,
            "brand_evidence": r.brand_evidence,
            "evidence": r.evidence.get("decision"),
        }
        for r in suspicious
    ]
    return summary


def run_manual_site_sheet(*, limit: int | None = None) -> dict:
    targets = _manual_site_targets()
    if limit:
        targets = targets[:limit]

    sheets = _sheets()
    sheets.ensure_sheet(TAB_MANUAL_SITE)
    sheets.clear(TAB_MANUAL_SITE)
    sheets.update(TAB_MANUAL_SITE, "A1:L1", [MANUAL_SITE_HEADERS])
    payload = [_manual_site_row(r) for r in targets]
    for off in range(0, len(payload), 500):
        chunk = payload[off : off + 500]
        sheets.update(
            TAB_MANUAL_SITE,
            f"A{off + 2}:L{off + len(chunk) + 1}",
            chunk,
            value_input_option="USER_ENTERED",
        )
    return {"sheet_tab": TAB_MANUAL_SITE, "uploaded": len(payload)}


def run_manual_site_promote(*, dry_run: bool = True, limit: int | None = None) -> dict:
    """Принять строки из вкладки ручного поиска сайта.

    Строка берётся только если approve содержит да/yes/1/true и заполнены
    inn + brand. Команда не пишет реквизиты сама: она обновляет state/сайт, а
    реальное создание реквизита делает существующий empty-apply с backup,
    BP verify и cleanup.
    """
    state = _load_state()
    rows = [PlanRow(**r) for r in state.get("results", [])]
    by_id = {r.company_id: r for r in rows}
    approved = _read_manual_site_approved()
    if limit:
        approved = approved[:limit]

    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    promoted = 0
    skipped_existing_failed = 0
    invalid: list[dict[str, str]] = []
    site_updates: list[dict[str, str]] = []

    for item in approved:
        row = by_id.get(item["company_id"])
        if not row:
            invalid.append({"company_id": item["company_id"], "error": "company_id not found in state"})
            continue
        inn = normalize_inn(item.get("inn"))
        brand = str(item.get("brand") or "").strip()
        if not is_valid_inn_format(inn):
            invalid.append({"company_id": row.company_id, "error": f"invalid inn: {item.get('inn')}"})
            continue
        if brand not in {"Belberry", "Acoola Team"}:
            invalid.append({"company_id": row.company_id, "error": f"invalid brand: {brand}"})
            continue

        new_site = str(item.get("new_site") or "").strip()
        old_manual_site = row.evidence.get("manual_site") if isinstance(row.evidence, dict) else {}
        if not isinstance(old_manual_site, dict):
            old_manual_site = {}
        unchanged_failed_manual_site = (
            row.source == "manual_site"
            and row.apply_status in {"BP_FAILED", "VERIFY_FAILED"}
            and str(old_manual_site.get("new_site") or "").strip() == new_site
            and str(old_manual_site.get("inn") or "").strip() == inn
            and str(old_manual_site.get("brand") or "").strip() == brand
        )
        if unchanged_failed_manual_site:
            skipped_existing_failed += 1
            continue

        if new_site and not dry_run:
            company_before = bx.get_company(row.company_id)
            reqs_before = bx.list_company_requisites(row.company_id) if company_before else []
            _backup_before_apply_snapshot(bx, row, company_before, reqs_before)
            bx.update_company(row.company_id, {"UF_CRM_5DEF838D882A2": new_site, "WEB": [{"VALUE": new_site, "VALUE_TYPE": "WORK"}]})
            site_updates.append({"company_id": row.company_id, "new_site": new_site})

        row.source = "manual_site"
        row.inn_candidate = inn
        row.geo_verified = True
        row.brand_predicted = brand
        row.brand_evidence = str(item.get("note") or "ручное подтверждение сайта/ИНН")
        row.classification = "READY_TO_APPLY"
        row.apply_status = ""
        row.evidence = {
            **(row.evidence or {}),
            "decision": "manual site approved: verified INN + brand",
            "manual_site": {
                "new_site": new_site,
                "inn": inn,
                "brand": brand,
                "note": item.get("note") or "",
            },
        }
        promoted += 1

    if not dry_run:
        state["results"] = [by_id[r.company_id].__dict__ for r in rows]
        state["ts_msk"] = _now()
        _write_json(STATE_JSON, state)
        _write_json(PLAN_JSON, state.get("results", []))
        run_upload_plan()
        run_manual_site_sheet()

    return {
        "dry_run": dry_run,
        "approved_rows": len(approved),
        "promoted": promoted,
        "skipped_existing_failed": skipped_existing_failed,
        "site_updates": site_updates,
        "invalid": invalid,
    }


def run_reconcile_existing(*, limit: int | None = None, throttle_s: float = 0.1) -> dict:
    """Сверить оставшийся план с текущими карточками Б24.

    Если компания уже имеет verified-реквизит (ИНН + ОГРН/ОГРНИП), это уже
    обогащённая карточка: проставляем бренд проекта и убираем строку из
    рабочей вкладки через apply_status=APPLIED.
    """
    state = _load_state()
    rows = [PlanRow(**r) for r in state.get("results", [])]
    targets = [r for r in rows if r.apply_status != "APPLIED"]
    targets.sort(key=lambda r: int(r.company_id))
    if limit:
        targets = targets[:limit]

    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    by_id = {r.company_id: r for r in rows}
    applied = 0
    company_deleted = 0
    no_verified = 0
    brand_updated = 0
    errors: list[dict[str, str]] = []
    by_brand = {"Belberry": 0, "Acoola Team": 0}
    examples: list[dict[str, str]] = []

    for off in range(0, len(targets), 25):
        chunk = targets[off : off + 25]
        commands: dict[str, tuple[str, dict]] = {}
        for row in chunk:
            commands[f"co_{row.company_id}"] = ("crm.company.get", {"id": row.company_id})
            commands[f"req_{row.company_id}"] = (
                "crm.requisite.list",
                {
                    "filter": {"ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY, "ENTITY_ID": row.company_id},
                    "select": ["ID", "ENTITY_ID", "RQ_INN", "RQ_OGRN", "RQ_OGRNIP"],
                    "start": -1,
                },
            )
        try:
            batch = bx.batch(commands)
        except Exception as exc:  # noqa: BLE001
            errors.append({"company_id": ",".join(r.company_id for r in chunk), "error": str(exc)[:300]})
            continue

        for row in chunk:
            company = batch.get(f"co_{row.company_id}")
            if not company:
                row.apply_status = "COMPANY_DELETED"
                company_deleted += 1
                continue

            reqs = batch.get(f"req_{row.company_id}") or []
            verified_req = _find_verified_requisite(reqs)
            if not verified_req:
                no_verified += 1
                continue

            brand, brand_evidence = _brand_from_existing_company(company, row)
            if company.get(UF_BRAND_FIELD) != brand:
                try:
                    bx.update_company(row.company_id, {UF_BRAND_FIELD: brand})
                    brand_updated += 1
                    if throttle_s > 0:
                        time.sleep(throttle_s)
                except Exception as exc:  # noqa: BLE001
                    errors.append({"company_id": row.company_id, "error": f"brand update failed: {exc}"[:300]})
                    continue

            row.source = row.source or "bitrix_existing_requisite"
            row.inn_candidate = str(verified_req.get("RQ_INN") or row.inn_candidate or "")
            row.geo_verified = True
            row.brand_predicted = brand
            row.brand_evidence = brand_evidence
            row.classification = "READY_TO_APPLY"
            row.apply_status = "APPLIED"
            row.evidence = {
                **(row.evidence or {}),
                "decision": "already enriched in Bitrix: verified requisite exists; brand reconciled",
                "bitrix_existing_requisite": {
                    "ID": verified_req.get("ID"),
                    "RQ_INN": verified_req.get("RQ_INN"),
                    "RQ_OGRN": verified_req.get("RQ_OGRN"),
                    "RQ_OGRNIP": verified_req.get("RQ_OGRNIP"),
                },
            }
            applied += 1
            by_brand[brand] += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "company_id": row.company_id,
                        "title": str(company.get("TITLE") or row.title),
                        "inn": str(verified_req.get("RQ_INN") or ""),
                        "ogrn": str(verified_req.get("RQ_OGRN") or verified_req.get("RQ_OGRNIP") or ""),
                        "brand": brand,
                    }
                )

        state["results"] = [by_id[r.company_id].__dict__ for r in rows]
        state["ts_msk"] = _now()
        _write_json(STATE_JSON, state)
        if throttle_s > 0:
            time.sleep(throttle_s)

    state["results"] = [by_id[r.company_id].__dict__ for r in rows]
    state["ts_msk"] = _now()
    _write_json(STATE_JSON, state)
    _write_json(PLAN_JSON, state.get("results", []))
    run_upload_plan()
    return {
        "checked": len(targets),
        "applied_existing": applied,
        "brand_updated": brand_updated,
        "company_deleted": company_deleted,
        "no_verified_requisite": no_verified,
        "applied_by_brand": by_brand,
        "examples": examples,
        "errors": errors,
    }


def run_apply(*, dry_run: bool = True, limit: int | None = None, throttle_s: float = CCE_APPLY_SLEEP_S) -> dict:
    """Apply только для READY_TO_APPLY из isolated plan.

    По умолчанию dry-run. Реальный write должен запускаться только после
    явного approve пользователя.
    """
    state = _load_state()
    rows = [PlanRow(**r) for r in state.get("results", [])]
    targets = [
        r for r in rows
        if r.classification == "READY_TO_APPLY"
        and r.apply_status not in {"APPLIED", "APPLIED_LIQUIDATED", "COMPANY_DELETED", "BP_FAILED", "VERIFY_FAILED"}
    ]
    targets.sort(key=lambda r: int(r.company_id))
    if limit:
        targets = targets[:limit]

    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    applied = 0
    applied_liquidated = 0
    skipped = 0
    bp_failed = 0
    verify_failed = 0
    company_deleted = 0
    by_brand = {"Belberry": 0, "Acoola Team": 0}
    success_examples: list[dict[str, str]] = []

    by_id = {r.company_id: r for r in rows}
    for idx, row in enumerate(targets, start=1):
        if idx > 1 and throttle_s > 0:
            time.sleep(throttle_s)

        inn = normalize_inn(row.inn_candidate)
        if not inn or not is_valid_inn_format(inn):
            row.apply_status = "VERIFY_FAILED"
            verify_failed += 1
            continue
        if row.brand_predicted not in by_brand:
            row.apply_status = "VERIFY_FAILED"
            verify_failed += 1
            continue

        try:
            all_same_inn_requisites = _list_requisites_by_inn(bx, inn)
        except Exception as exc:  # noqa: BLE001
            print(f"[empty-apply] company {row.company_id}: duplicate_check_failed: {exc}")
            all_same_inn_requisites = []
            row.duplicate_check_failed = True
        duplicate_info = _duplicate_info_from_requisites(bx, all_same_inn_requisites, row.company_id)
        duplicate_info_for_backup = duplicate_info if _has_duplicate_info(duplicate_info) else None
        _attach_duplicate_info(row, duplicate_info_for_backup)
        if duplicate_info.get("duplicate_active_deals"):
            first_deal = duplicate_info["duplicate_active_deals"][0]
            print(
                f"[empty-apply] company {row.company_id}: duplicate_active_deal: "
                f"{first_deal.get('deal_id')}@{first_deal.get('company_id')}"
            )

        company_before = bx.get_company(row.company_id)
        existing = bx.list_company_requisites(row.company_id)
        if not company_before:
            backup_path = _backup_before_apply_snapshot(
                bx,
                row,
                company_before,
                existing,
                duplicate_info=duplicate_info_for_backup,
            )
            print(f"[empty-apply] backup company {row.company_id}: {backup_path}")
            row.apply_status = "COMPANY_DELETED"
            company_deleted += 1
            continue

        this_company_requisites = [
            req for req in all_same_inn_requisites
            if str(req.get("ENTITY_ID") or "").strip() == str(row.company_id)
        ]
        if not this_company_requisites:
            this_company_requisites = [
                req for req in existing
                if normalize_inn(req.get("RQ_INN")) == inn
            ]

        matching_existing_inn = [
            req for req in existing
            if str(req.get("RQ_INN") or "").strip() == inn
        ]
        if not matching_existing_inn:
            matching_existing_inn = list(this_company_requisites)
        if matching_existing_inn:
            verified_req = _find_verified_requisite(matching_existing_inn)
            if verified_req:
                row.apply_status = "APPLIED"
                applied += 1
                by_brand[row.brand_predicted] += 1
                bx.update_company(row.company_id, {UF_BRAND_FIELD: row.brand_predicted})
                continue
            if dry_run:
                print(
                    f"[empty-apply] DRY-RUN company {row.company_id}: "
                    f"existing RQ_INN={inn}; start BP and verify"
                )
                row.apply_status = "DRY_RUN"
                continue
            backup_path = _backup_before_apply_snapshot(
                bx,
                row,
                company_before,
                existing,
                duplicate_info=duplicate_info_for_backup,
            )
            print(f"[empty-apply] backup company {row.company_id}: {backup_path}")
            if CCE_COMPANY_TOUCH:
                _touch_company(bx, row.company_id)
            wf = _start_bp_update(bx, row.company_id)
            if wf.startswith("failed:"):
                row.apply_status = "BP_FAILED"
                bp_failed += 1
                continue
            verified, verified_req, apply_status = _verify_with_retries(bx, row.company_id)
            if verified:
                bx.update_company(row.company_id, {UF_BRAND_FIELD: row.brand_predicted})
                cleanup_deleted = _cleanup_trigger_requisites(bx, row.company_id, inn)
                row.apply_status = apply_status
                applied += 1
                filled_address = _fill_company_address_fields(
                    bx,
                    row.company_id,
                    bx.get_company(row.company_id) or {},
                )
                if filled_address:
                    print(f"[empty-apply] company {row.company_id}: address_fields_filled: {filled_address}")
                if apply_status == "APPLIED_LIQUIDATED":
                    applied_liquidated += 1
                by_brand[row.brand_predicted] += 1
                if len(success_examples) < 2:
                    success_examples.append(
                        {
                            "company_id": row.company_id,
                            "inn": inn,
                            "rq_ogrn": str((verified_req or {}).get("RQ_OGRN") or (verified_req or {}).get("RQ_OGRNIP") or ""),
                            "brand": row.brand_predicted,
                            "cleanup_deleted": str(cleanup_deleted),
                        }
                    )
            else:
                row.apply_status = "BP_FAILED"
                bp_failed += 1
            continue

        existing_same_inn = list(this_company_requisites)
        verified_existing = _find_verified_requisite(existing_same_inn)
        if verified_existing:
            bx.update_company(row.company_id, {UF_BRAND_FIELD: row.brand_predicted})
            cleanup_deleted = _cleanup_trigger_requisites(bx, row.company_id, inn)
            row.apply_status = "APPLIED"
            applied += 1
            by_brand[row.brand_predicted] += 1
            if len(success_examples) < 2:
                success_examples.append(
                    {
                        "company_id": row.company_id,
                        "inn": inn,
                        "rq_ogrn": str(verified_existing.get("RQ_OGRN") or verified_existing.get("RQ_OGRNIP") or ""),
                        "brand": row.brand_predicted,
                        "cleanup_deleted": str(cleanup_deleted),
                    }
                )
            continue

        preset_id = CCE_PRESET_ID
        payload = {
            "ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY,
            "ENTITY_ID": int(row.company_id),
            "PRESET_ID": int(preset_id),
            "NAME": "Реквизиты ЮЛ",
            "RQ_INN": inn,
        }
        if dry_run:
            print(
                f"[empty-apply] DRY-RUN company {row.company_id}: "
                f"crm.requisite.add={json.dumps(payload, ensure_ascii=False)}; "
                f"crm.company.update={{'{UF_BRAND_FIELD}': '{row.brand_predicted}'}}"
            )
            row.apply_status = "DRY_RUN"
            continue

        req_id = ""
        try:
            backup_path = _backup_before_apply_snapshot(
                bx,
                row,
                company_before,
                existing,
                duplicate_info=duplicate_info_for_backup,
            )
            print(f"[empty-apply] backup company {row.company_id}: {backup_path}")
            had_requisites_before = bool(existing)
            if not existing_same_inn:
                req_id = bx.add_requisite(payload)
            if CCE_COMPANY_TOUCH:
                _touch_company(bx, row.company_id)
            if not had_requisites_before:
                wf_first = _start_bp_first_entry(bx, row.company_id)
                if wf_first.startswith("failed:"):
                    row.apply_status = "BP_FAILED"
                    bp_failed += 1
                    _rollback_added_requisite(bx, req_id)
                    continue
                if wf_first.startswith("triggered:") and CCE_BIZPROC_WAIT_S > 0:
                    time.sleep(min(CCE_BIZPROC_WAIT_S, 3))
            wf_update = _start_bp_update(bx, row.company_id)
            if wf_update.startswith("failed:"):
                row.apply_status = "BP_FAILED"
                bp_failed += 1
                _rollback_added_requisite(bx, req_id)
                continue
            if wf_update.startswith("triggered:") and CCE_BIZPROC_WAIT_S > 0:
                time.sleep(CCE_BIZPROC_WAIT_S)
            verified, verified_req, apply_status = _verify_with_retries(bx, row.company_id)
            if verified:
                bx.update_company(row.company_id, {UF_BRAND_FIELD: row.brand_predicted})
                cleanup_deleted = _cleanup_trigger_requisites(bx, row.company_id, inn)
                row.apply_status = apply_status
                applied += 1
                filled_address = _fill_company_address_fields(
                    bx,
                    row.company_id,
                    bx.get_company(row.company_id) or {},
                )
                if filled_address:
                    print(f"[empty-apply] company {row.company_id}: address_fields_filled: {filled_address}")
                if apply_status == "APPLIED_LIQUIDATED":
                    applied_liquidated += 1
                by_brand[row.brand_predicted] += 1
                if len(success_examples) < 2:
                    success_examples.append(
                        {
                            "company_id": row.company_id,
                            "inn": inn,
                            "rq_ogrn": str((verified_req or {}).get("RQ_OGRN") or (verified_req or {}).get("RQ_OGRNIP") or ""),
                            "brand": row.brand_predicted,
                            "cleanup_deleted": str(cleanup_deleted),
                        }
                    )
            else:
                row.apply_status = "BP_FAILED"
                bp_failed += 1
                _rollback_added_requisite(bx, req_id)
        except Exception as exc:  # noqa: BLE001
            if _is_entity_not_found_add_error(exc):
                row.apply_status = "COMPANY_DELETED"
                company_deleted += 1
                print(f"[empty-apply] company {row.company_id}: COMPANY_DELETED: {exc}")
                continue
            row.apply_status = "VERIFY_FAILED"
            verify_failed += 1
            if req_id:
                _rollback_added_requisite(bx, req_id)
            print(f"[empty-apply] company {row.company_id}: VERIFY_FAILED: {exc}")

    state["results"] = [by_id[r.company_id].__dict__ for r in rows]
    state["ts_msk"] = _now()
    _write_json(STATE_JSON, state)
    if not dry_run:
        run_upload_plan()
    return {
        "dry_run": dry_run,
        "targets": len(targets),
        "applied": applied,
        "applied_liquidated": applied_liquidated,
        "skipped": skipped,
        "bp_failed": bp_failed,
        "verify_failed": verify_failed,
        "company_deleted": company_deleted,
        "applied_by_brand": by_brand,
        "success_examples": success_examples,
    }


def _brand_from_existing_company(company: dict[str, Any], row: PlanRow) -> tuple[str, str]:
    title = " ".join(
        str(x or "") for x in (
            company.get("TITLE"),
            company.get("UF_CRM_1737098414068"),
            company.get("UF_CRM_1737098422264"),
            row.title,
        )
    )
    domain = str(company.get("UF_CRM_5DEF838D882A2") or "")
    if not domain and isinstance(row.evidence, dict):
        signals = row.evidence.get("signals") if isinstance(row.evidence.get("signals"), dict) else {}
        domain = str(signals.get("domain") or signals.get("uf_site") or "")
    brand, evidence, confident = classify_brand({"title": title, "value": title}, title=title, domain=domain)
    if confident:
        return brand, evidence
    return "Acoola Team", "verified-реквизит уже есть в Б24; медицинских признаков нет"


def _enrich_one(raw: dict[str, Any], *, dadata: "DadataClient", checko: "CheckoClient", rusprofile: "RusprofileClient") -> PlanRow:
    cid = str(raw["id"])
    title = str(raw.get("title") or "")
    score = int(raw.get("score") or 0)
    evidence: dict[str, Any] = {"signals": _signals(raw), "attempts": []}

    candidates: list[LookupCandidate] = []
    domain = _clean_domain(raw.get("domain") or raw.get("web") or "")
    phone = _clean_phone(raw.get("phone") or "")

    if domain and dadata:
        candidates.extend(dadata.find_by_domain(domain, evidence))
    if domain and not candidates:
        candidates.extend(_find_inn_on_domain_site(domain, evidence))
    if domain and not candidates and EMPTY_ENABLE_CHECKO:
        candidates.extend(checko.find_by_domain(domain, evidence))
    if not candidates and phone and dadata:
        candidates.extend(dadata.find_by_phone(phone, evidence))
    if not candidates and title and raw.get("has_legal_name"):
        candidates.extend(rusprofile.search_by_name(title, evidence))

    if not candidates:
        return PlanRow(
            company_id=cid,
            title=title,
            score=score,
            classification="NO_INN_FOUND",
            evidence={**evidence, "decision": "ИНН не найден"},
        )

    unique_inns = {c.inn for c in candidates if c.inn}
    if len(unique_inns) != 1:
        return _manual(cid, title, score, candidates[0], evidence, "несколько ИНН-кандидатов")

    cand = candidates[0]
    geo_verified = cand.source in {"dadata_domain", "dadata_phone", "checko_domain"}
    if cand.source == "rusprofile":
        geo_verified = _geo_verify(cand, raw)
        if not geo_verified:
            return _manual(cid, title, score, cand, evidence, "rusprofile без geo-verification")

    brand, brand_evidence, brand_confident = classify_brand(cand.payload, title=title, domain=domain)
    if not brand_confident:
        return _manual(cid, title, score, cand, evidence, "бренд неоднозначен", brand=brand, brand_evidence=brand_evidence)

    return PlanRow(
        company_id=cid,
        title=title,
        score=score,
        source=cand.source,
        inn_candidate=cand.inn,
        geo_verified=geo_verified,
        brand_predicted=brand,
        brand_evidence=brand_evidence,
        classification="READY_TO_APPLY",
        evidence={**evidence, "candidate": cand.to_evidence(), "decision": "verified INN + confident brand"},
    )


def _manual(
    cid: str,
    title: str,
    score: int,
    cand: "LookupCandidate",
    evidence: dict[str, Any],
    reason: str,
    *,
    brand: str = "",
    brand_evidence: str = "",
) -> PlanRow:
    return PlanRow(
        company_id=cid,
        title=title,
        score=score,
        source=cand.source,
        inn_candidate=cand.inn,
        geo_verified=False,
        brand_predicted=brand,
        brand_evidence=brand_evidence,
        classification="MANUAL",
        evidence={**evidence, "candidate": cand.to_evidence(), "decision": reason},
    )


@dataclass
class LookupCandidate:
    source: str
    inn: str
    name: str = ""
    ogrn: str = ""
    address: str = ""
    okved: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_evidence(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "inn": self.inn,
            "name": self.name,
            "ogrn": self.ogrn,
            "address": self.address,
            "okved": self.okved,
        }


class DadataClient:
    def __init__(self, token: str, secret: str | None = None):
        self.token = token
        self.secret = secret
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if secret:
            self.session.headers.update({"X-Secret": secret})

    @classmethod
    def from_env(cls, *, required: bool = True) -> "DadataClient | None":
        _load_env(WORKSPACE_ROOT / ".env.integrations")
        token = os.environ.get("DADATA_TOKEN", "").strip()
        secret = os.environ.get("DADATA_SECRET", "").strip() or None
        if not token:
            if not required:
                return None
            raise RuntimeError("DADATA_TOKEN не найден в .env.integrations или окружении")
        return cls(token, secret)

    def find_by_domain(self, domain: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        return self._find("findByDomain", domain, "dadata_domain", evidence)

    def find_by_phone(self, phone: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        return self._find("findByPhone", phone, "dadata_phone", evidence)

    def _find(self, method: str, query: str, source: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        url = f"https://suggestions.dadata.ru/suggestions/api/4_1/rs/{method}/party"
        try:
            resp = self.session.post(url, json={"query": query}, timeout=20)
            evidence["attempts"].append({"source": source, "query": query, "status": resp.status_code})
            if resp.status_code == 404:
                return self._suggest(query, source, evidence)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            evidence["attempts"].append({"source": source, "query": query, "error": str(exc)[:300]})
            return []
        return _candidates_from_dadata(data.get("suggestions") or [], source)

    def _suggest(self, query: str, source: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
        try:
            resp = self.session.post(url, json={"query": query, "count": 5}, timeout=20)
            evidence["attempts"].append({"source": f"{source}_suggest_fallback", "query": query, "status": resp.status_code})
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            evidence["attempts"].append({"source": f"{source}_suggest_fallback", "query": query, "error": str(exc)[:300]})
            return []
        return _candidates_from_dadata(data.get("suggestions") or [], source)


class CheckoClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 Cloudbot enrichment"})

    def find_by_domain(self, domain: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        url = f"https://checko.ru/search?query={domain}"
        try:
            resp = self.session.get(url, timeout=EMPTY_FALLBACK_TIMEOUT_S)
            evidence["attempts"].append({"source": "checko_domain", "query": domain, "status": resp.status_code})
            if resp.status_code >= 400:
                return []
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            evidence["attempts"].append({"source": "checko_domain", "query": domain, "error": str(exc)[:300]})
            return []
        inn = _extract_labeled(text, "ИНН")
        if not inn:
            return []
        return [LookupCandidate(source="checko_domain", inn=inn, name=_html_title(text), payload={"html": text[:5000]})]


class RusprofileClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 Cloudbot enrichment"})

    def search_by_name(self, title: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
        from urllib.parse import quote_plus

        url = f"https://www.rusprofile.ru/search?query={quote_plus(title)}"
        try:
            resp = self.session.get(url, timeout=EMPTY_FALLBACK_TIMEOUT_S)
            evidence["attempts"].append({"source": "rusprofile", "query": title, "status": resp.status_code})
            if resp.status_code >= 400:
                return []
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            evidence["attempts"].append({"source": "rusprofile", "query": title, "error": str(exc)[:300]})
            return []
        inn = _extract_labeled(text, "ИНН")
        if not inn:
            return []
        payload = {"html": text[:8000], "address": _extract_address(text)}
        return [LookupCandidate(source="rusprofile", inn=inn, name=_html_title(text) or title, address=payload["address"], payload=payload)]


def _find_inn_on_domain_site(domain: str, evidence: dict[str, Any]) -> list[LookupCandidate]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 Cloudbot enrichment"})
    base = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    for path in EMPTY_WEB_PATHS:
        url = base.rstrip("/") + path
        try:
            resp = session.get(url, timeout=EMPTY_WEB_TIMEOUT_S, allow_redirects=True)
            evidence["attempts"].append({"source": "web_requisites", "query": url, "status": resp.status_code})
        except requests.exceptions.SSLError:
            try:
                resp = session.get(url, timeout=EMPTY_WEB_TIMEOUT_S, allow_redirects=True, verify=False)
                evidence["attempts"].append({"source": "web_requisites_ssl_unsafe", "query": url, "status": resp.status_code})
            except Exception as exc:  # noqa: BLE001
                evidence["attempts"].append({"source": "web_requisites", "query": url, "error": str(exc)[:300]})
                continue
        except Exception as exc:  # noqa: BLE001
            evidence["attempts"].append({"source": "web_requisites", "query": url, "error": str(exc)[:300]})
            if path == "/":
                break
            continue
        if resp.status_code >= 400:
            continue
        inn = extract_inn_from_text(resp.text, source_url=resp.url or url)
        if inn:
            return [
                LookupCandidate(
                    source="web_requisites",
                    inn=inn,
                    name=extract_company_name_from_html(resp.text) or "",
                    payload={"url": resp.url or url, "title": extract_company_name_from_html(resp.text) or ""},
                )
            ]
        time.sleep(0.05)
    return []


def classify_brand(payload: dict[str, Any], *, title: str = "", domain: str = "") -> tuple[str, str, bool]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    okveds = data.get("okveds") or []
    main_okved = str(data.get("okved") or "")
    name_data = data.get("name") if isinstance(data.get("name"), dict) else {}
    names = " ".join(
        str(x or "") for x in (
            title,
            domain,
            data.get("value"),
            data.get("unrestricted_value"),
            data.get("title"),
            name_data.get("full"),
            name_data.get("short"),
        )
    ).lower()

    codes = [main_okved] + [str(o.get("code") or "") for o in okveds if isinstance(o, dict)]
    for code in codes:
        if code and any(code.startswith(prefix) for prefix in MEDICAL_OKVED_PREFIXES):
            return "Belberry", f"ОКВЭД {code}", True

    for kw in MEDICAL_KEYWORDS:
        if kw in names:
            return "Belberry", f"название/домен содержит '{kw}'", True

    domain_l = (domain or "").lower()
    for hint in DOMAIN_MEDICAL_HINTS:
        if hint in domain_l:
            return "Belberry", f"медицинский домен: {hint}", True

    for kw in NON_MEDICAL_KEYWORDS:
        if kw in names:
            return "Acoola Team", f"не-медицинский маркер '{kw}'", True

    if main_okved:
        return "Acoola Team", f"ОКВЭД {main_okved} не медицинский", True

    return "Acoola Team", "нет медицинского ОКВЭД/ключевых слов", False


def _candidates_from_dadata(suggestions: list[dict[str, Any]], source: str) -> list[LookupCandidate]:
    out = []
    for item in suggestions:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        inn = normalize_inn(data.get("inn"))
        if not inn:
            continue
        addr = data.get("address") if isinstance(data.get("address"), dict) else {}
        name = data.get("name") if isinstance(data.get("name"), dict) else {}
        out.append(
            LookupCandidate(
                source=source,
                inn=inn,
                name=str(name.get("full_with_opf") or name.get("full") or item.get("value") or ""),
                ogrn=str(data.get("ogrn") or ""),
                address=str(addr.get("unrestricted_value") or addr.get("value") or ""),
                okved=str(data.get("okved") or ""),
                payload=item,
            )
        )
    return out


def _existing_inn_ids(bx: BitrixClient, company_ids: list[str]) -> set[str]:
    out: set[str] = set()
    commands: dict[str, tuple[str, dict]] = {}
    for cid in company_ids:
        commands[f"req_{cid}"] = (
            "crm.requisite.list",
            {
                "filter": {"ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY, "ENTITY_ID": cid},
                "select": ["ID", "ENTITY_ID", "RQ_INN"],
                "start": -1,
            },
        )
        if len(commands) == 50:
            _collect_existing(bx.batch(commands), out)
            commands = {}
            time.sleep(0.1)
    if commands:
        _collect_existing(bx.batch(commands), out)
    return out


def _collect_existing(batch_result: dict[str, Any], out: set[str]) -> None:
    for records in batch_result.values():
        if not isinstance(records, list):
            continue
        for req in records:
            if isinstance(req, dict) and is_valid_inn_format(req.get("RQ_INN")):
                out.add(str(req.get("ENTITY_ID")))


def _read_do_not_touch_deal_ids(sheets: SheetsClient) -> set[str]:
    titles = sheets.get_sheet_titles()
    if TAB_DO_NOT_TOUCH not in titles:
        raise RuntimeError(
            f"Вкладка исключений {TAB_DO_NOT_TOUCH!r} не найдена в таблице {SHEET_ID}. "
            f"Доступные вкладки: {titles}. Задай CCE_EMPTY_DO_NOT_TOUCH_TAB или добавь вкладку."
        )
    rows = sheets.read(TAB_DO_NOT_TOUCH, "B2:B834", unformatted=True)
    ids: set[str] = set()
    for raw in rows:
        for cell in raw:
            s = str(cell).strip()
            if re.fullmatch(r"\d{2,10}", s):
                ids.add(s)
    return ids


def _deal_ids_to_company_ids(bx: BitrixClient, deal_ids: set[str]) -> set[str]:
    """Защищённые сделки → защищённые company_id.

    Лист `Не трогать` содержит deal_id в колонке B. Если сделка относится к
    аккаунтингу/retention, то связанную компанию тоже нельзя обогащать и
    менять бренд/реквизиты.
    """
    out: set[str] = set()
    ids = sorted(deal_ids, key=int)
    commands: dict[str, tuple[str, dict]] = {}
    command_idx = 0
    for off in range(0, len(ids), 50):
        chunk = ids[off : off + 50]
        commands[f"deals_{command_idx}"] = (
            "crm.deal.list",
            {
                "filter": {"@ID": chunk},
                "select": ["ID", "COMPANY_ID"],
                "start": -1,
            },
        )
        command_idx += 1
        if len(commands) == 50:
            _collect_deal_company_ids(bx.batch(commands), out)
            commands = {}
            time.sleep(0.1)
    if commands:
        _collect_deal_company_ids(bx.batch(commands), out)
    return out


def _collect_deal_company_ids(batch_result: dict[str, Any], out: set[str]) -> None:
    for records in batch_result.values():
        if not isinstance(records, list):
            continue
        for deal in records:
            if not isinstance(deal, dict):
                continue
            cid = str(deal.get("COMPANY_ID") or "").strip()
            if cid and cid != "0":
                out.add(cid)


def _geo_verify(cand: LookupCandidate, raw: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(x or "").lower()
        for x in (cand.address, cand.payload.get("address"), cand.payload.get("html"), cand.name)
    )
    hints = []
    for field in ("uf_city", "uf_site"):
        if raw.get(field):
            hints.append(str(raw[field]).lower())
    phone = _clean_phone(raw.get("phone") or "")
    if len(phone) >= 4:
        code = phone[1:4] if phone.startswith("7") else phone[:3]
        hints.extend(PHONE_CITY_HINTS.get(code, ()))
    hints = [h for h in hints if len(h) >= 4]
    if not hints:
        return False
    return any(h in haystack for h in hints)


def _summary(rows: list[PlanRow]) -> dict[str, Any]:
    ready = [r for r in rows if r.classification == "READY_TO_APPLY"]
    manual = [r for r in rows if r.classification == "MANUAL"]
    no_inn = [r for r in rows if r.classification == "NO_INN_FOUND"]
    return {
        "total_results": len(rows),
        "ready_to_apply": len(ready),
        "manual": len(manual),
        "no_inn_found": len(no_inn),
        "ready_by_brand": {
            "Belberry": sum(1 for r in ready if r.brand_predicted == "Belberry"),
            "Acoola Team": sum(1 for r in ready if r.brand_predicted == "Acoola Team"),
        },
    }


def _signals(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(raw.get("title") or ""),
        "phone": str(raw.get("phone") or ""),
        "web": str(raw.get("web") or ""),
        "domain": str(raw.get("domain") or ""),
        "uf_city": str(raw.get("uf_city") or ""),
        "uf_site": str(raw.get("uf_site") or ""),
    }


def _manual_site_row(row: PlanRow) -> list[str]:
    signals = row.evidence.get("signals") if isinstance(row.evidence, dict) else {}
    if not isinstance(signals, dict):
        signals = {}
    manual_site = row.evidence.get("manual_site") if isinstance(row.evidence, dict) else {}
    if not isinstance(manual_site, dict):
        manual_site = {}
    phone = str(signals.get("phone") or "")
    old_site = str(signals.get("domain") or signals.get("web") or signals.get("uf_site") or "")
    city = str(signals.get("uf_city") or "")
    title = row.title or f"company #{row.company_id}"
    search_phone = _search_link(f"{phone} {title} сайт ИНН реквизиты") if phone else ""
    search_domain = _search_link(f"{old_site} ИНН ОГРН реквизиты") if old_site else ""
    new_site = str(manual_site.get("new_site") or "")
    inn = str(manual_site.get("inn") or row.inn_candidate or "")
    brand = str(manual_site.get("brand") or row.brand_predicted or "")
    note = str(manual_site.get("note") or "")
    approve = ""
    if row.source == "manual_site" and row.classification == "READY_TO_APPLY":
        approve = "да"
        if row.apply_status and row.apply_status != "APPLIED":
            note = f"{row.apply_status}: {note}".strip(": ")
    return [
        company_link(row.company_id, title),
        str(row.score),
        phone,
        old_site,
        city,
        search_phone,
        search_domain,
        new_site,
        inn,
        brand,
        approve,
        note,
    ]


def _read_manual_site_approved() -> list[dict[str, str]]:
    rows = _sheets().read(TAB_MANUAL_SITE, "A1:L10000", unformatted=False)
    if not rows:
        return []
    headers = [str(h).strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}
    fallback_targets = _manual_site_targets()
    out: list[dict[str, str]] = []
    for row_offset, raw in enumerate(rows[1:]):
        approve = _cell(raw, idx, "approve").strip().lower()
        if approve not in {"да", "yes", "y", "1", "true", "ok", "approve", "approved"}:
            continue
        company_cell = _cell(raw, idx, "company")
        cid = _extract_company_id(company_cell)
        if not cid:
            cid = _fallback_manual_site_company_id(raw, idx, fallback_targets, row_offset)
        if not cid:
            continue
        out.append(
            {
                "company_id": cid,
                "new_site": _cell(raw, idx, "new_site").strip(),
                "inn": _cell(raw, idx, "inn").strip(),
                "brand": _cell(raw, idx, "brand").strip(),
                "note": _cell(raw, idx, "note").strip(),
            }
        )
    return out


def _manual_site_targets() -> list[PlanRow]:
    rows = [PlanRow(**r) for r in _load_state().get("results", [])]
    targets = [
        r for r in rows
        if r.apply_status not in {"APPLIED", "APPLIED_LIQUIDATED", "COMPANY_DELETED"}
        and (
            r.classification in {"NO_INN_FOUND", "MANUAL"}
            or (r.classification == "READY_TO_APPLY" and r.source == "manual_site")
        )
    ]
    targets.sort(key=lambda r: (-int(r.score or 0), int(r.company_id)))
    return targets


def _fallback_manual_site_company_id(
    raw: list[Any],
    idx: dict[str, int],
    targets: list[PlanRow],
    row_offset: int,
) -> str:
    """Определить company_id, если Sheets вернул только текст гиперссылки.

    Вкладка генерируется из state в стабильном порядке. При чтении через
    FORMATTED_VALUE Google отдаёт текст ссылки без URL, поэтому ID компании
    недоступен. Fallback допустим только если текущая строка совпадает с
    ожидаемой строкой state по названию/телефону/сайту.
    """
    if row_offset < 0 or row_offset >= len(targets):
        return ""
    target = targets[row_offset]
    expected = _manual_site_row(target)
    checks = (
        _norm_cell(_cell(raw, idx, "company")) == _norm_company_display(expected[0]),
        _clean_phone(_cell(raw, idx, "phone")) == _clean_phone(expected[2]),
        _clean_domain(_cell(raw, idx, "old_site")) == _clean_domain(expected[3]),
    )
    meaningful_checks = [
        ok for ok, value in zip(checks, (expected[0], expected[2], expected[3]))
        if str(value or "").strip()
    ]
    if meaningful_checks and all(meaningful_checks):
        return target.company_id
    return ""


def _norm_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _norm_company_display(value: str) -> str:
    m = re.search(r'=HYPERLINK\("[^"]+";"(.*)"\)$', str(value or ""))
    if m:
        return _norm_cell(m.group(1).replace('""', '"'))
    return _norm_cell(value)


def _cell(row: list[Any], idx: dict[str, int], key: str) -> str:
    pos = idx.get(key, -1)
    if pos < 0 or pos >= len(row):
        return ""
    return str(row[pos] or "")


def _extract_company_id(value: str) -> str:
    m = re.search(r"/crm/company/details/(\d+)/", str(value))
    if m:
        return m.group(1)
    return ""


def _search_link(query: str) -> str:
    from urllib.parse import quote_plus

    url = f"https://www.google.com/search?q={quote_plus(query)}"
    return f'=HYPERLINK("{url}";"поиск")'


def _extract_labeled(text: str, label: str) -> str:
    m = re.search(rf"{label}\s*[:№]?\s*(\d{{10}}(?:\d{{2}})?)", text, re.IGNORECASE)
    return normalize_inn(m.group(1)) if m else ""


def _extract_address(text: str) -> str:
    m = re.search(r"(?:Адрес|Юридический адрес)[^:]*:\s*([^<\n]{5,300})", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _html_title(text: str) -> str:
    m = re.search(r"<title[^>]*>([^<]{3,250})</title>", text, re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _clean_domain(value: str) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"^https?://", "", s).split("/", 1)[0].strip()
    return s


def _clean_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return digits


def _read_input() -> list[dict[str, Any]]:
    return json.loads(INPUT_PATH.read_text(encoding="utf-8"))


def _load_state() -> dict[str, Any]:
    if not STATE_JSON.exists():
        raise RuntimeError(f"state не найден: {STATE_JSON}. Сначала запусти empty-discover")
    return json.loads(STATE_JSON.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _sheets() -> SheetsClient:
    return SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _now() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def _touch_company(bx: BitrixClient, company_id: str) -> None:
    import uuid

    company = bx.get_company(company_id) or {}
    comments = company.get("COMMENTS") or ""
    bx.update_company(company_id, {"COMMENTS": f"{comments}\n[touch {uuid.uuid4().hex[:8]}]"})


def _start_bp_first_entry(bx: BitrixClient, company_id: str) -> str:
    if not CCE_BIZPROC_FIRST_ENTRY_ID:
        return "skipped:first_entry_bp_disabled"
    return _start_bp_template(bx, company_id, CCE_BIZPROC_FIRST_ENTRY_ID)


def start_bp_first_entry(bx: BitrixClient, company_id: str) -> str:
    """Публичная обёртка запуска первого BP-обогащения компании."""
    return _start_bp_first_entry(bx, company_id)


def _start_bp_update(bx: BitrixClient, company_id: str) -> str:
    if not CCE_BIZPROC_UPDATE_ID:
        return "skipped:update_bp_disabled"
    return _start_bp_template(bx, company_id, CCE_BIZPROC_UPDATE_ID)


def start_bp_update(bx: BitrixClient, company_id: str) -> str:
    """Публичная обёртка запуска основного BP-обновления компании."""
    return _start_bp_update(bx, company_id)


def _start_bp_template(bx: BitrixClient, company_id: str, template_id: int) -> str:
    doc = ["crm", "CCrmDocumentCompany", f"COMPANY_{company_id}"]
    try:
        result = bx.start_workflow(template_id, doc)
        return f"triggered:{str(result.get('workflow_id') or 'started')}"
    except Exception as exc:  # noqa: BLE001
        return f"failed:{str(exc)[:120]}"


def _verify_with_retries(bx: BitrixClient, company_id: str) -> tuple[bool, dict | None, str]:
    for attempt in range(3):
        time.sleep(45)
        company = bx.get_company(company_id) or {}
        reqs = bx.list_company_requisites(company_id)
        verified_req = _find_verified_requisite(reqs)
        organization_status = str(company.get("UF_CRM_ORG_STATUS") or "").strip()
        # Ликвидированная компания — валидный итог второго BP: дальше ретраи
        # не нужны, сделку в работу для неё запускать нельзя.
        if organization_status == "8852":
            return True, verified_req, "APPLIED_LIQUIDATED"
        if verified_req:
            return True, verified_req, "APPLIED"
        if attempt < 2:
            if CCE_COMPANY_TOUCH:
                _touch_company(bx, company_id)
            _start_bp_update(bx, company_id)
    return False, None, "BP_FAILED"


def verify_with_retries(bx: BitrixClient, company_id: str) -> tuple[bool, dict | None, str]:
    """Публичная обёртка проверки результата BP-обогащения."""
    return _verify_with_retries(bx, company_id)


def _fill_company_address_fields(bx: BitrixClient, company_id: str, company: dict) -> dict[str, Any]:
    """Заполнить город/область компании из юридического адреса, не затирая ручной ввод."""
    raw_address = _clean(
        company.get("REG_ADDRESS")
        or company.get("ADDRESS")
        or company.get(COMPANY_UF_LEGAL_ADDRESS)
    )
    fallback_city, fallback_region = _city_region_from_address(raw_address)
    reg_city = _clean(company.get("REG_ADDRESS_CITY") or company.get("ADDRESS_CITY") or fallback_city)
    reg_region = _clean(company.get("REG_ADDRESS_REGION") or company.get("ADDRESS_REGION") or fallback_region)
    updates: dict[str, Any] = {}
    if COMPANY_UF_CITY and reg_city and not _clean(company.get(COMPANY_UF_CITY)):
        updates[COMPANY_UF_CITY] = reg_city
    if COMPANY_UF_REGION and reg_region and not _clean(company.get(COMPANY_UF_REGION)):
        region_value = (
            _resolve_region_enum(reg_region, COMPANY_REGION_ENUM_MAP)
            if COMPANY_REGION_ENUM_MAP
            else reg_region
        )
        if region_value:
            updates[COMPANY_UF_REGION] = region_value
    if updates:
        bx.update_company(company_id, updates)
    return updates


def fill_company_address_fields(bx: BitrixClient, company_id: str, company: dict) -> dict[str, Any]:
    """Публичная обёртка заполнения города/области компании из адреса."""
    return _fill_company_address_fields(bx, company_id, company)


def _resolve_region_enum(raw_region: str, mapping: dict[str, str]) -> str:
    norm = _normalize_region_key(raw_region)
    return mapping.get(norm, "")


def _city_region_from_address(address: str) -> tuple[str, str]:
    """Достать город и регион из полной строки адреса, если BP не дал структурные поля."""
    text = _clean(address)
    if not text:
        return "", ""
    lowered = text.lower()
    federal_cities = {
        "москва": "Москва",
        "санкт-петербург": "Санкт-Петербург",
        "севастополь": "Севастополь",
    }
    for key, label in federal_cities.items():
        if re.search(rf"\bг\.?\s*{re.escape(key)}\b|\b{re.escape(key)}\b", lowered):
            return label, label
    city_match = re.search(r"\bг\.?\s*([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z\-\s]+?)(?:,|$)", text)
    city = _clean(city_match.group(1)) if city_match else ""
    region_match = re.search(
        r"\b([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z\-\s]+?(?:область|край|республика|автономный округ|АО))(?:,|$)",
        text,
        re.IGNORECASE,
    )
    region = _clean(region_match.group(1)) if region_match else ""
    return city, region


def _normalize_region_key(raw_region: str) -> str:
    norm = _clean(raw_region).lower()
    norm = re.sub(r"\([^)]*\)", "", norm)
    norm = re.split(r"\s+[—-]\s+", norm, maxsplit=1)[0]
    replacements = (
        ("автономный округ", ""),
        ("народная", ""),
        ("республика", ""),
        ("область", ""),
        ("край", ""),
        ("обл.", ""),
        ("обл ", ""),
        ("респ.", ""),
        ("респ ", ""),
        ("ао", ""),
        ("г.", ""),
        ("город ", ""),
    )
    for token, replacement in replacements:
        norm = norm.replace(token, replacement)
    return re.sub(r"\s+", " ", norm).strip(" .,-")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _find_verified_requisite(requisites: list[dict]) -> dict | None:
    for req in requisites or []:
        if str(req.get("RQ_OGRN") or req.get("RQ_OGRNIP") or "").strip():
            return req
    return None


def _list_requisites_by_inn(bx: BitrixClient, inn: str) -> list[dict]:
    if hasattr(bx, "list_requisites_by_inn"):
        return bx.list_requisites_by_inn(inn)
    if hasattr(bx, "search_requisite_by_inn"):
        return bx.search_requisite_by_inn(inn)
    return []


def _duplicate_info_from_requisites(
    bx: BitrixClient,
    requisites: list[dict],
    current_company_id: str,
) -> dict[str, Any]:
    current_company_id = str(current_company_id)
    duplicate_requisites = [
        req for req in requisites or []
        if str(req.get("ENTITY_ID") or "").strip() and str(req.get("ENTITY_ID") or "").strip() != current_company_id
    ]
    duplicate_company_ids = sorted({str(req.get("ENTITY_ID")) for req in duplicate_requisites}, key=lambda x: int(x) if x.isdigit() else x)
    duplicate_requisite_ids = sorted(str(req.get("ID")) for req in duplicate_requisites if str(req.get("ID") or "").strip())
    duplicate_active_deals: list[dict[str, str]] = []
    for company_id in duplicate_company_ids:
        for deal in _list_active_deals_for_duplicate_company(bx, company_id):
            duplicate_active_deals.append(deal)

    reason = ""
    if duplicate_active_deals:
        first = duplicate_active_deals[0]
        reason = f"enrich-only: active deal {first.get('deal_id')} on company {first.get('company_id')}"
    elif duplicate_company_ids:
        reason = "enrich duplicate: same inn requisites on companies " + ", ".join(duplicate_company_ids)

    return {
        "duplicate_company_ids": duplicate_company_ids,
        "duplicate_active_deals": duplicate_active_deals,
        "duplicate_requisite_ids": duplicate_requisite_ids,
        "duplicate_reason": reason,
    }


def duplicate_info_from_requisites(
    bx: BitrixClient,
    requisites: list[dict],
    current_company_id: str,
) -> dict[str, Any]:
    """Публичная обёртка анализа дублей по реквизитам с тем же ИНН."""
    return _duplicate_info_from_requisites(bx, requisites, current_company_id)


def _has_duplicate_info(duplicate_info: dict[str, Any]) -> bool:
    return bool(
        duplicate_info.get("duplicate_company_ids")
        or duplicate_info.get("duplicate_active_deals")
        or duplicate_info.get("duplicate_requisite_ids")
        or duplicate_info.get("duplicate_reason")
    )


def _list_active_deals_for_duplicate_company(bx: BitrixClient, company_id: str) -> list[dict[str, str]]:
    if not hasattr(bx, "list_company_deals"):
        return []
    deals = bx.list_company_deals(
        str(company_id),
        select=["ID", "COMPANY_ID", "STAGE_ID", "CATEGORY_ID", "CLOSED"],
    )
    out: list[dict[str, str]] = []
    for deal in deals or []:
        if str(deal.get("CLOSED") or "N") == "Y":
            continue
        if str(deal.get("STAGE_ID") or "") in TELEMARKETING_REFUSAL_STAGE_IDS:
            continue
        out.append(
            {
                "company_id": str(deal.get("COMPANY_ID") or company_id),
                "deal_id": str(deal.get("ID") or ""),
                "stage_id": str(deal.get("STAGE_ID") or ""),
                "category_id": str(deal.get("CATEGORY_ID") or ""),
            }
        )
    return out


def _attach_duplicate_info(row: PlanRow, duplicate_info: dict[str, Any] | None) -> None:
    row.duplicate_company_ids = [str(x) for x in (duplicate_info or {}).get("duplicate_company_ids", [])]
    row.duplicate_active_deals = list((duplicate_info or {}).get("duplicate_active_deals", []))
    row.duplicate_requisite_ids = [str(x) for x in (duplicate_info or {}).get("duplicate_requisite_ids", [])]
    row.duplicate_reason = str((duplicate_info or {}).get("duplicate_reason") or "")
    evidence = dict(row.evidence or {})
    if duplicate_info is None:
        evidence.pop("duplicate_info", None)
    else:
        evidence["duplicate_info"] = {
            "duplicate_company_ids": row.duplicate_company_ids,
            "duplicate_active_deals": row.duplicate_active_deals,
            "duplicate_requisite_ids": row.duplicate_requisite_ids,
            "duplicate_reason": row.duplicate_reason,
        }
    row.evidence = evidence


def _backup_before_apply_snapshot(
    bx: BitrixClient,
    row: PlanRow,
    company_before: dict | None,
    requisites_before: list[dict],
    duplicate_info: dict | None = None,
) -> str:
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    path = WORKSPACE_ROOT / f"belberry/bitrix24/backups/enrich_apply_{row.company_id}_{ts}.json"
    payload = {
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "company_id": row.company_id,
        "plan_row": row.__dict__,
        "company_before": company_before,
        "requisites_before": requisites_before,
    }
    if duplicate_info is not None:
        payload["duplicate_info"] = duplicate_info
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path)


def _cleanup_trigger_requisites(bx: BitrixClient, company_id: str, inn: str) -> int:
    reqs = bx.list_company_requisites(company_id)
    keeper = _find_verified_requisite(reqs)
    if not keeper:
        return 0
    deleted = 0
    for req in reqs:
        if str(req.get("RQ_INN") or "").strip() != inn:
            continue
        if str(req.get("RQ_OGRN") or req.get("RQ_OGRNIP") or "").strip():
            continue
        rid = str(req.get("ID") or "").strip()
        if not rid:
            continue
        try:
            if bx.delete_requisite(rid):
                deleted += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[empty-apply] cleanup delete_requisite({rid}) failed: {exc}")
    return deleted


def _is_entity_not_found_add_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "crm.requisite.add" in msg
        and (
            "entity not found" in msg
            or "not found" in msg
            or "http 400" in msg
        )
    )


def _rollback_added_requisite(bx: BitrixClient, requisite_id: str) -> None:
    if not requisite_id:
        return
    try:
        bx.delete_requisite(str(requisite_id))
    except Exception as exc:  # noqa: BLE001
        print(f"[empty-apply] rollback delete_requisite({requisite_id}) failed: {exc}")
