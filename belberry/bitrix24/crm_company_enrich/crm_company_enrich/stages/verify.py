"""Стадия verify — read-only проверка APPLIED_PENDING_BP строк.

Контракт:

Для каждой строки company_enrich_queue в статусе APPLIED_PENDING_BP:
  - bx.list_company_requisites(row.company_id);
  - если есть реквизит с непустым RQ_OGRN → APPLIED + error_message обновляется
    маркером verify=enriched(req=<id>);
  - иначе → остаётся APPLIED_PENDING_BP, error_message=«bp did not enrich
    after retry, manual check needed».

Verify можно вызывать многократно — никаких write-операций в Bitrix.
Только Sheets-update на APPLIED-промоушн.

Note: для APPLIED строк (где apply уже подтвердил bp_verify_enriched=true)
verify не делает ничего — это terminal-статус.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..sheet_store import read_queue, replace_row, update_row
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _find_enriched_requisite_id(requisites: list[dict]) -> str:
    """Возвращает ID реквизита с непустым RQ_OGRN либо ''."""
    for req in requisites or []:
        ogrn = str(req.get("RQ_OGRN") or "").strip()
        if ogrn:
            return str(req.get("ID") or "")
    return ""


def run(
    bx: BitrixClient | None = None,
    sheets: SheetsClient | None = None,
    *,
    limit: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Verify APPLIED_PENDING_BP строки. Возвращает summary-дикт."""
    if bx is None or sheets is None:
        from ..bitrix_client import BitrixClient as _BX
        from ..config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
        from ..sheets_client import SheetsClient as _SH

        bx = bx or _BX(state_path=STATE_PATH, log_path=LOG_PATH)
        sheets = sheets or _SH(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)

    now = now or datetime.now(MOSCOW_TZ)
    queue = read_queue(sheets)

    promoted = 0
    still_pending = 0
    examined = 0

    for row_number, row in queue:
        if row.status != Status.APPLIED_PENDING_BP:
            continue
        examined += 1
        if limit is not None and examined > limit:
            break

        try:
            reqs = bx.list_company_requisites(row.company_id)
        except Exception as exc:  # noqa: BLE001 — verify read-only best-effort
            print(f"[verify] company {row.company_id}: list failed: {exc} — skip")
            continue

        enriched_id = _find_enriched_requisite_id(reqs)
        if enriched_id:
            new_msg = f"verify=enriched(req={enriched_id}) at {now.isoformat(timespec='seconds')}"
            updated = replace_row(
                row,
                status=Status.APPLIED,
                last_action_at=now,
                error_message=new_msg,
            )
            update_row(sheets, row_number, updated)
            promoted += 1
            print(f"[verify] company {row.company_id}: APPLIED_PENDING_BP → APPLIED (req={enriched_id})")
        else:
            new_msg = (
                f"bp did not enrich after retry, manual check needed "
                f"(checked at {now.isoformat(timespec='seconds')})"
            )
            updated = replace_row(
                row,
                last_action_at=now,
                error_message=new_msg,
            )
            update_row(sheets, row_number, updated)
            still_pending += 1
            print(f"[verify] company {row.company_id}: still pending (no OGRN)")

    summary = {
        "examined": examined,
        "promoted": promoted,
        "still_pending": still_pending,
        "ts_msk": now.isoformat(timespec="seconds"),
    }
    print(
        f"[verify] examined={examined} promoted={promoted} "
        f"still_pending={still_pending}"
    )
    return summary
