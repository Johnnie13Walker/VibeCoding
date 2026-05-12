"""Стадия apply — WRITE в Bitrix: создаёт реквизит для APPROVED + CREATE_REQ строк.

Контракт (см. также docstring run()):

1. Источник: company_enrich_queue, status=APPROVED, target_action=CREATE_REQ.
   Прочие target_action в этой итерации не обрабатываются:
     - MERGE_INTO   → пропускаем с сообщением «merge_dupes not implemented yet»
                       (строка остаётся в статусе APPROVED).
     - SKIP_ALREADY → помечаем status=SKIPPED без write.
2. Safety guards (любой → строка abort, никакого add):
     - in_active_deal_merge=1
     - is_valid_inn_format(discovered_inn) == False
     - approved != 1
     - в Bitrix у компании УЖЕ есть реквизит с валидным RQ_INN
       (race condition guard: повторный crm.requisite.list).
3. Backup: перед каждой попыткой write в Sheets-таб enrich_backup пишется строка
   ts_utc, company_id, action, payload_json, existing_requisites_json,
   applied_status, error_message. Идемпотентно (append-only). В dry-run snapshot
   только печатается, в таб не пишется.
4. Write: crm.requisite.add c PRESET_ID из ENV CCE_PRESET_ID (default 1).
5. Bizproc (best-effort): bizproc.workflow.start если CCE_BIZPROC_TEMPLATE_ID
   задан; иначе bizproc_status=not_configured.
6. Status: success → APPLIED, failure → FAILED.
   Идемпотентность: строки со status ∈ {APPLIED, FAILED, SKIPPED, DONE, MERGED,
   VERIFIED, ROLLED_BACK} пропускаются (не понижаем статус).
7. Rate-limit: time.sleep(CCE_APPLY_SLEEP_S) между write-вызовами.

dry-run: ничего в Bitrix не пишет, status в Sheets НЕ меняет, backup-таб НЕ
обновляется, печатает план в stdout (включая будущий payload).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient, BitrixError
from ..config import (
    CCE_APPLY_SLEEP_S,
    CCE_BIZPROC_TEMPLATE_ID,
    CCE_PRESET_ID,
    ENTITY_TYPE_COMPANY,
    TAB_BACKUP,
)
from ..models import (
    QueueRow,
    TargetAction,
    clean_company_name_for_requisite,
    is_valid_inn_format,
    normalize_inn,
)
from ..sheet_store import read_queue, replace_row, update_row
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Колонки backup-таба
BACKUP_HEADERS = [
    "ts_utc",
    "company_id",
    "action",
    "payload_json",
    "existing_requisites_json",
    "applied_status",
    "error_message",
]

# Статусы, в которых apply уже считает строку «обработанной» (idempotency).
TERMINAL_STATUSES = frozenset(
    {
        Status.APPLIED,
        Status.FAILED,
        Status.SKIPPED,
        Status.MERGED,
        Status.VERIFIED,
        Status.DONE,
        Status.ROLLED_BACK,
    }
)

# Sentinel-объект для bizproc_template_id (отличать «не передано» от «явно None»).
_BIZPROC_SENTINEL: Any = object()


@dataclass
class ApplyOutcome:
    company_id: str
    row_number: int
    target_action: str
    applied_status: str  # APPLIED / SKIPPED / FAILED / DRY_RUN / NOOP
    requisite_id: str | None = None
    bizproc_status: str = "not_configured"  # not_configured | triggered:<id> | failed:<msg>
    error_message: str = ""
    payload: dict | None = None
    existing_requisites: list | None = None


# ----- public API -----


def run(
    bx: BitrixClient | None = None,
    sheets: SheetsClient | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    sleep_s: float | None = None,
    now: datetime | None = None,
    preset_id: int | None = None,
    bizproc_template_id: Any = _BIZPROC_SENTINEL,
) -> dict:
    """Выполнить apply-стадию. Для прод-CLI передаются клиенты; в тестах — фейки.

    bizproc_template_id: sentinel-механизм нужен, чтобы тест мог явно передать
    None (= «не настроено») или int (= «настроено»), не полагаясь на ENV.
    """
    if bx is None or sheets is None:
        from ..bitrix_client import BitrixClient as _BX
        from ..config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
        from ..sheets_client import SheetsClient as _SH

        bx = bx or _BX(state_path=STATE_PATH, log_path=LOG_PATH)
        sheets = sheets or _SH(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)

    sleep_s = CCE_APPLY_SLEEP_S if sleep_s is None else sleep_s
    preset_id = CCE_PRESET_ID if preset_id is None else preset_id
    if bizproc_template_id is _BIZPROC_SENTINEL:
        bizproc_template_id = CCE_BIZPROC_TEMPLATE_ID
    now = now or datetime.now(MOSCOW_TZ)

    queue = read_queue(sheets)
    targets = _select_targets(queue, limit=limit)

    applied = 0
    skipped_already_has_requisite = 0
    skipped_active_merge = 0
    skipped_other_action = 0
    failed = 0
    bizproc_triggered = 0
    bizproc_not_configured = 0
    bizproc_failed = 0

    # Backup-таб подготавливается лениво: только если действительно есть
    # CREATE_REQ-кандидаты И не dry-run.
    backup_ready = False

    is_first_write = True
    for row_number, row in targets:
        # idempotency guard
        if row.status in TERMINAL_STATUSES:
            continue

        # ----- safety guards (по приоритету) -----
        if row.target_action == TargetAction.SKIP_ALREADY:
            if not dry_run:
                _update(
                    sheets,
                    row_number,
                    row,
                    status=Status.SKIPPED,
                    last_action_at=now,
                    error_message=None,
                )
            else:
                print(f"[apply] DRY-RUN: company {row.company_id} → SKIP_ALREADY → SKIPPED")
            continue

        if row.target_action == TargetAction.MERGE_INTO:
            print(
                f"[apply] company {row.company_id}: target_action=MERGE_INTO — "
                f"merge_dupes not implemented yet, leaving row as APPROVED"
            )
            skipped_other_action += 1
            continue

        if row.target_action != TargetAction.CREATE_REQ:
            print(
                f"[apply] company {row.company_id}: target_action="
                f"{row.target_action.value if row.target_action else '∅'} — "
                f"not handled by this stage, skip"
            )
            skipped_other_action += 1
            continue

        if row.in_active_deal_merge:
            print(
                f"[apply] company {row.company_id}: in_active_deal_merge=1 → skip"
            )
            if not dry_run:
                _update(
                    sheets,
                    row_number,
                    row,
                    status=Status.FAILED,
                    last_action_at=now,
                    error_message="row in active deal-merge",
                )
            skipped_active_merge += 1
            failed += 1
            continue

        if not row.approved:
            print(
                f"[apply] company {row.company_id}: approved=0 → skip"
            )
            skipped_other_action += 1
            continue

        inn_norm = normalize_inn(row.discovered_inn)
        if not is_valid_inn_format(inn_norm):
            msg = f"invalid inn format: {row.discovered_inn!r}"
            print(f"[apply] company {row.company_id}: {msg}")
            if not dry_run:
                _update(
                    sheets,
                    row_number,
                    row,
                    status=Status.FAILED,
                    last_action_at=now,
                    error_message=msg,
                )
            failed += 1
            continue

        # ----- race-condition guard: компания уже имеет валидный реквизит? -----
        existing = bx.list_company_requisites(row.company_id)
        already_valid = [r for r in existing if is_valid_inn_format(r.get("RQ_INN"))]
        if already_valid:
            msg = (
                f"already has valid requisite "
                f"(RQ_INN={already_valid[0].get('RQ_INN')!r})"
            )
            print(f"[apply] company {row.company_id}: {msg}")
            if not dry_run:
                _update(
                    sheets,
                    row_number,
                    row,
                    status=Status.SKIPPED,
                    last_action_at=now,
                    error_message=msg,
                )
            skipped_already_has_requisite += 1
            continue

        # ----- build payload -----
        payload = _build_payload(
            company_id=row.company_id,
            inn=inn_norm,
            discovered_name=row.discovered_name,
            discovered_source=row.discovered_source,
            bitrix_title=row.company_name,
            preset_id=preset_id,
        )

        outcome = ApplyOutcome(
            company_id=row.company_id,
            row_number=row_number,
            target_action=TargetAction.CREATE_REQ.value,
            applied_status="PENDING",
            payload=payload,
            existing_requisites=existing,
        )

        if dry_run:
            print(
                f"[apply] DRY-RUN company {row.company_id}: would call "
                f"crm.requisite.add with payload={json.dumps(payload, ensure_ascii=False)}"
            )
            outcome.applied_status = "DRY_RUN"
            _print_backup_row(outcome, now)
            continue

        # Lazy-init backup tab (single attempt for this run).
        if not backup_ready:
            _ensure_backup_sheet(sheets)
            backup_ready = True

        # Rate-limit между write-вызовами (на первом — пропускаем sleep).
        if not is_first_write and sleep_s > 0:
            time.sleep(sleep_s)
        is_first_write = False

        # ----- WRITE -----
        try:
            requisite_id = bx.add_requisite(payload)
            outcome.requisite_id = requisite_id
            outcome.applied_status = "APPLIED"
        except BitrixError as exc:
            outcome.applied_status = "FAILED"
            outcome.error_message = f"crm.requisite.add failed: {exc}"
            _append_backup_row(sheets, outcome, now)
            _update(
                sheets,
                row_number,
                row,
                status=Status.FAILED,
                last_action_at=now,
                error_message=outcome.error_message,
            )
            failed += 1
            continue

        # ----- bizproc (best-effort) -----
        bp_status = _trigger_bizproc(bx, row.company_id, bizproc_template_id)
        outcome.bizproc_status = bp_status
        if bp_status == "not_configured":
            bizproc_not_configured += 1
        elif bp_status.startswith("triggered"):
            bizproc_triggered += 1
        else:
            bizproc_failed += 1

        _append_backup_row(sheets, outcome, now)
        _update(
            sheets,
            row_number,
            row,
            status=Status.APPLIED,
            last_action_at=now,
            error_message=f"requisite_id={requisite_id}; bizproc={bp_status}",
        )
        applied += 1

    summary = {
        "applied": applied,
        "skipped_already_has_requisite": skipped_already_has_requisite,
        "skipped_active_merge": skipped_active_merge,
        "skipped_other_action": skipped_other_action,
        "failed": failed,
        "bizproc": {
            "triggered": bizproc_triggered,
            "not_configured": bizproc_not_configured,
            "failed": bizproc_failed,
        },
        "ts_msk": now.isoformat(timespec="seconds"),
        "dry_run": dry_run,
    }
    print(
        f"[apply] applied={applied} skipped_already_has_requisite="
        f"{skipped_already_has_requisite} skipped_active_merge={skipped_active_merge} "
        f"skipped_other_action={skipped_other_action} failed={failed} "
        f"bizproc=(triggered={bizproc_triggered} not_configured={bizproc_not_configured} "
        f"failed={bizproc_failed}) dry_run={dry_run}"
    )
    return summary


# ----- internals -----


def _select_targets(
    queue: list[tuple[int, QueueRow]],
    *,
    limit: int | None,
) -> list[tuple[int, QueueRow]]:
    """Отобрать APPROVED строки. Идемпотентность: terminal-статусы skip."""
    out: list[tuple[int, QueueRow]] = []
    for row_number, row in queue:
        if row.status in TERMINAL_STATUSES:
            continue
        if row.status != Status.APPROVED:
            continue
        out.append((row_number, row))
        if limit is not None and len(out) >= limit:
            break
    return out


def _build_payload(
    *,
    company_id: str,
    inn: str,
    discovered_name: str | None,
    discovered_source: str | None,
    bitrix_title: str,
    preset_id: int,
) -> dict:
    """Сконструировать поля для crm.requisite.add.

    Правила:
      - PRESET_ID = preset_id (default 1, обычно «ЮЛ»).
      - RQ_COMPANY_NAME_FULL:
          • если discovered_source == "rusprofile" и есть discovered_name —
            используем (rusprofile даёт точное юр.название);
          • если ИНН 10 цифр и discovered_name пустой — оставляем пустым
            (рискованно ставить случайное название юрлица);
          • иначе → discovered_name or bitrix_title.
        В любом случае значение прогоняется через clean_company_name_for_requisite
        (снятие SEO-хвостов rusprofile, HTML-entities, HTML-title trail). Если
        после чистки осталось пусто/мусор — RQ_COMPANY_NAME_FULL не выставляется,
        и bizproc позже подтянет название из ЕГРЮЛ.
      - NAME — человекочитаемый ярлык реквизита.
    """
    clean_discovered = clean_company_name_for_requisite(discovered_name)
    clean_bitrix = clean_company_name_for_requisite(bitrix_title)

    if discovered_source == "rusprofile" and clean_discovered:
        rq_company_name = clean_discovered
    elif len(inn) == 10 and not clean_discovered:
        rq_company_name = ""  # ЮЛ без точного имени → не выдумываем
    else:
        rq_company_name = clean_discovered or clean_bitrix or ""

    payload: dict[str, Any] = {
        "ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY,
        "ENTITY_ID": int(company_id),
        "PRESET_ID": int(preset_id),
        "NAME": "Реквизиты ЮЛ" if len(inn) == 10 else "Реквизиты ИП",
        "RQ_INN": inn,
    }
    if rq_company_name:
        payload["RQ_COMPANY_NAME_FULL"] = rq_company_name
    return payload


def _trigger_bizproc(
    bx: BitrixClient,
    company_id: str,
    template_id: int | None,
) -> str:
    """Безопасно дернуть bizproc.workflow.start. Возвращает строку для bizproc_status.

    Никогда не кидает — все ошибки → "failed: <msg>".
    """
    if not template_id:
        return "not_configured"
    document_type = ["crm", "CCrmDocumentCompany", f"COMPANY_{company_id}"]
    try:
        result = bx.start_workflow(template_id=int(template_id), document_type=document_type)
    except Exception as exc:  # noqa: BLE001 — best-effort
        return f"failed: {exc}"
    wf_id = result.get("workflow_id", "") if isinstance(result, dict) else str(result)
    return f"triggered: {wf_id}"


def _update(
    sheets: SheetsClient,
    row_number: int,
    row: QueueRow,
    **changes,
) -> None:
    updated = replace_row(row, **changes)
    update_row(sheets, row_number, updated)


def _ensure_backup_sheet(sheets: SheetsClient) -> None:
    """Идемпотентно: создать вкладку enrich_backup + заголовки, если ещё нет."""
    sheets.ensure_sheet(TAB_BACKUP)
    existing = sheets.read(TAB_BACKUP, "A1:Z1")
    if not existing or not existing[0]:
        sheets.update(TAB_BACKUP, "A1", [BACKUP_HEADERS])


def _append_backup_row(
    sheets: SheetsClient,
    outcome: ApplyOutcome,
    now: datetime,
) -> None:
    ts_utc = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    row = [
        ts_utc,
        outcome.company_id,
        outcome.target_action,
        json.dumps(outcome.payload or {}, ensure_ascii=False),
        json.dumps(outcome.existing_requisites or [], ensure_ascii=False),
        outcome.applied_status,
        outcome.error_message or (
            f"requisite_id={outcome.requisite_id}; bizproc={outcome.bizproc_status}"
            if outcome.requisite_id
            else ""
        ),
    ]
    sheets.append(TAB_BACKUP, [row])


def _print_backup_row(outcome: ApplyOutcome, now: datetime) -> None:
    """Для dry-run — печатаем что бы записали в backup, без actual write."""
    ts_utc = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(
        f"[apply] DRY-RUN backup row: ts_utc={ts_utc} company_id={outcome.company_id} "
        f"action={outcome.target_action} payload={json.dumps(outcome.payload, ensure_ascii=False)}"
    )
