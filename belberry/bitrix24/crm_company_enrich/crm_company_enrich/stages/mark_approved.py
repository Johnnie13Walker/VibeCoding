"""Стадия mark-approved — переводит CLASSIFIED строки в APPROVED.

WRITE — только Sheets. Никакого Bitrix-write.

Режимы:
  --all --status CLASSIFIED     → массовый approve (фильтр по target_action)
  --company-id X --action ACT   → апрув одной строки с явным action
  --company-id X --action MERGE_INTO --target Y → апрув + установка merge_target

Safety:
  - MERGE_INTO требует, чтобы у target company был реквизит с RQ_INN
    (read-only проверка через bx.list_company_requisites). Иначе error_message.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..models import TargetAction, is_valid_inn_format
from ..sheet_store import read_queue, replace_row, update_row
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(
    sheets: SheetsClient,
    *,
    bx: BitrixClient | None = None,
    all_: bool = False,
    status: str = "CLASSIFIED",
    company_id: str | None = None,
    action: str | None = None,
    target: str | None = None,
    limit: int | None = None,
) -> dict:
    now = datetime.now(MOSCOW_TZ)
    target_status = Status(status)
    approved_count = 0
    errors: list[str] = []

    queue = read_queue(sheets)
    for row_number, row in queue:
        if row.status != target_status:
            continue
        if row.in_active_deal_merge:
            continue
        if limit is not None and approved_count >= limit:
            break

        if not all_:
            if not company_id:
                raise ValueError("Передайте --all или --company-id")
            if str(row.company_id) != str(company_id):
                continue
            if action is not None:
                try:
                    desired_action = TargetAction(action)
                except ValueError as exc:
                    raise ValueError(f"Неизвестный action: {action}") from exc
            else:
                desired_action = row.target_action

            if desired_action == TargetAction.MERGE_INTO:
                merge_target = target or row.merge_target_company_id
                if not merge_target:
                    raise ValueError("MERGE_INTO требует --target или уже выставленный merge_target")
                if bx is None:
                    raise ValueError("MERGE_INTO requires bx client for target verification")
                if not _target_has_valid_inn(bx, merge_target):
                    err = f"target company {merge_target} has no valid INN — отклоняем approve"
                    errors.append(err)
                    update_row(
                        sheets,
                        row_number,
                        replace_row(
                            row,
                            target_action=TargetAction.MERGE_INTO,
                            merge_target_company_id=merge_target,
                            error_message=err,
                            last_action_at=now,
                        ),
                    )
                    continue
                row = replace_row(row, target_action=TargetAction.MERGE_INTO, merge_target_company_id=merge_target)
            elif desired_action is not None:
                row = replace_row(row, target_action=desired_action)
        else:
            # --all: пропускаем строки без подтверждённого target_action
            if row.target_action is None or row.target_action == TargetAction.SKIP_NO_INN:
                continue
            # для MERGE_INTO в --all тоже проверим, что target имеет реквизит
            if row.target_action == TargetAction.MERGE_INTO:
                if not row.merge_target_company_id:
                    continue
                if bx is None:
                    continue  # без bx не верифицировать target
                if not _target_has_valid_inn(bx, row.merge_target_company_id):
                    err = f"target company {row.merge_target_company_id} has no valid INN"
                    errors.append(err)
                    update_row(
                        sheets,
                        row_number,
                        replace_row(row, error_message=err, last_action_at=now),
                    )
                    continue

        update_row(
            sheets,
            row_number,
            replace_row(
                row,
                status=Status.APPROVED,
                approved=True,
                approved_by="company-enrich CLI",
                approved_at=now,
                last_action_at=now,
                error_message=None,
            ),
        )
        approved_count += 1

    print(f"[mark-approved] APPROVED: {approved_count}; errors: {len(errors)}")
    return {"approved": approved_count, "errors": errors}


def _target_has_valid_inn(bx: BitrixClient, company_id: str) -> bool:
    reqs = bx.list_company_requisites(company_id)
    return any(is_valid_inn_format(r.get("RQ_INN")) for r in reqs)
