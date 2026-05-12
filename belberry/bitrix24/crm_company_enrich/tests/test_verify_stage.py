"""Offline тесты verify-стадии.

Покрытие:
  1. APPLIED_PENDING_BP → APPLIED когда у компании появился реквизит с RQ_OGRN.
  2. APPLIED_PENDING_BP → APPLIED_PENDING_BP когда BP ещё не подтянул данные;
     error_message обновляется маркером manual check needed.
  3. APPLIED строки игнорируются (terminal).
  4. limit=1 ограничивает обработку.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from crm_company_enrich.config import TAB_QUEUE
from crm_company_enrich.models import QUEUE_HEADERS, QueueRow, TargetAction
from crm_company_enrich.stages import verify
from crm_company_enrich.state import Status

MSK = ZoneInfo("Europe/Moscow")


class FakeBitrix:
    def __init__(self, requisites_by_cid: dict[str, list[dict]]):
        self.requisites_by_cid = requisites_by_cid
        self.list_calls: list[str] = []

    def list_company_requisites(self, company_id: str) -> list[dict]:
        self.list_calls.append(str(company_id))
        return list(self.requisites_by_cid.get(str(company_id), []))


class FakeSheets:
    def __init__(self, rows: list[QueueRow]):
        self._rows = [r.to_sheet_row() for r in rows]
        self.updates: list[tuple[str, str, list[list[str]]]] = []

    def read(self, sheet: str, *args, **kwargs):
        if sheet == TAB_QUEUE:
            return [QUEUE_HEADERS, *self._rows]
        return []

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs):
        self.updates.append((sheet, range_, rows))
        if sheet == TAB_QUEUE and range_.startswith("A") and ":" in range_:
            n = int(range_.split(":")[0][1:])
            idx = n - 2
            if 0 <= idx < len(self._rows):
                self._rows[idx] = rows[0]

    def append(self, *args, **kwargs):
        pass

    def ensure_sheet(self, *args, **kwargs):
        pass

    def batch_update(self, *args, **kwargs):
        pass

    def clear(self, *args, **kwargs):
        pass

    def queue_row(self, idx: int) -> QueueRow:
        return QueueRow.from_sheet_row(self._rows[idx], QUEUE_HEADERS)


def _pending_row(cid: str = "10") -> QueueRow:
    return QueueRow(
        company_id=cid,
        company_name=f"Bitrix-title {cid}",
        discovered_inn="7707083893",
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPLIED_PENDING_BP,
        approved=True,
    )


def test_verify_promotes_when_ogrn_appears():
    row = _pending_row(cid="10")
    bx = FakeBitrix(
        requisites_by_cid={
            "10": [
                {"ID": "300", "RQ_INN": "7707083893", "RQ_OGRN": ""},  # наш
                {"ID": "301", "RQ_INN": "7707083893", "RQ_OGRN": "1027700132195"},  # BP
            ]
        }
    )
    sheets = FakeSheets([row])
    now = datetime(2026, 5, 12, 10, 0, tzinfo=MSK)

    summary = verify.run(bx, sheets, now=now)

    assert summary["examined"] == 1
    assert summary["promoted"] == 1
    assert summary["still_pending"] == 0
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED
    assert "verify=enriched(req=301)" in (updated.error_message or "")
    assert bx.list_calls == ["10"]


def test_verify_keeps_pending_when_no_ogrn():
    row = _pending_row(cid="10")
    bx = FakeBitrix(
        requisites_by_cid={
            "10": [{"ID": "300", "RQ_INN": "7707083893", "RQ_OGRN": ""}]
        }
    )
    sheets = FakeSheets([row])
    now = datetime(2026, 5, 12, 10, 0, tzinfo=MSK)

    summary = verify.run(bx, sheets, now=now)

    assert summary["examined"] == 1
    assert summary["promoted"] == 0
    assert summary["still_pending"] == 1
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED_PENDING_BP
    assert "manual check needed" in (updated.error_message or "")


def test_verify_ignores_applied_rows():
    row = _pending_row(cid="10")
    row.status = Status.APPLIED
    bx = FakeBitrix(requisites_by_cid={"10": []})
    sheets = FakeSheets([row])

    summary = verify.run(bx, sheets)
    assert summary["examined"] == 0
    assert summary["promoted"] == 0
    assert bx.list_calls == []


def test_verify_limit_respected():
    rows = [_pending_row(cid=str(i)) for i in (10, 20, 30)]
    bx = FakeBitrix(
        requisites_by_cid={
            "10": [{"ID": "1", "RQ_OGRN": "1027700132195"}],
            "20": [{"ID": "2", "RQ_OGRN": "1027700132196"}],
            "30": [{"ID": "3", "RQ_OGRN": "1027700132197"}],
        }
    )
    sheets = FakeSheets(rows)

    summary = verify.run(bx, sheets, limit=2)
    # examined увеличивается перед лимитом, поэтому промоутятся первые 2
    assert summary["promoted"] == 2
    assert sheets.queue_row(2).status == Status.APPLIED_PENDING_BP  # третья не тронута
