"""Offline тесты гибридного apply: touch + BP + verify.

Покрывает (см. README write-стадии «hybrid apply»):

  1. happy path — touch + start_workflow + verify=enriched → APPLIED.
  2. BP запустился, verify=not_enriched → APPLIED_PENDING_BP.
  3. BP не настроен (CCE_BIZPROC_TEMPLATE_ID=None) → нет touch/BP/verify.
  4. BP failed (start_workflow raises) → status=APPLIED, no verify.
  5. CCE_COMPANY_TOUCH=False → не вызывает update_company.
  6. dry-run — ничего не пишется, ни touch ни BP не запускаются.
  7. time.sleep замокан monkeypatch'ем (тесты не висят 15s).

Дополнительно: backup-таб содержит bp_workflow_id, bp_verify_enriched,
enriched_requisite_id; header расширен до 10 колонок.
"""
from __future__ import annotations

import pytest

from crm_company_enrich.bitrix_client import BitrixError
from crm_company_enrich.config import TAB_BACKUP, TAB_QUEUE
from crm_company_enrich.models import QUEUE_HEADERS, QueueRow, TargetAction
from crm_company_enrich.stages import apply
from crm_company_enrich.stages.apply import BACKUP_HEADERS
from crm_company_enrich.state import Status


# ----- Fakes -----


class FakeBitrix:
    """Расширенный fake: поддерживает update_company, get_company, и
    динамически меняет результат list_company_requisites после start_workflow
    (имитация: BP добавил 2-й реквизит с RQ_OGRN).
    """

    def __init__(
        self,
        existing_requisites: dict[str, list[dict]] | None = None,
        post_workflow_requisites: dict[str, list[dict]] | None = None,
        company_data: dict[str, dict] | None = None,
        add_result_id: str = "12345",
        workflow_result: dict | None = None,
        raise_on_add: Exception | None = None,
        raise_on_workflow: Exception | None = None,
        raise_on_update_company: Exception | None = None,
    ):
        self.existing = dict(existing_requisites or {})
        self.post_workflow = dict(post_workflow_requisites or {})
        self.company_data = dict(company_data or {})
        self.add_result_id = add_result_id
        self.workflow_result = workflow_result or {"workflow_id": "wf-777"}
        self.raise_on_add = raise_on_add
        self.raise_on_workflow = raise_on_workflow
        self.raise_on_update_company = raise_on_update_company

        self.add_calls: list[dict] = []
        self.list_calls: list[str] = []
        self.workflow_calls: list[tuple[int, list]] = []
        self.update_company_calls: list[tuple[str, dict]] = []
        self.get_company_calls: list[str] = []
        self._workflow_started: set[str] = set()

    def get_company(self, company_id: str) -> dict | None:
        self.get_company_calls.append(str(company_id))
        return self.company_data.get(str(company_id), {"ID": str(company_id), "COMMENTS": ""})

    def update_company(self, company_id: str, fields: dict) -> bool:
        if self.raise_on_update_company is not None:
            raise self.raise_on_update_company
        self.update_company_calls.append((str(company_id), dict(fields)))
        return True

    def list_company_requisites(self, company_id: str) -> list[dict]:
        cid = str(company_id)
        self.list_calls.append(cid)
        # Если для этой компании workflow уже запущен И есть post-workflow
        # данные — возвращаем post-workflow (имитация BP добавил реквизит).
        if cid in self._workflow_started and cid in self.post_workflow:
            return list(self.post_workflow[cid])
        return list(self.existing.get(cid, []))

    def add_requisite(self, fields: dict) -> str:
        self.add_calls.append(dict(fields))
        if self.raise_on_add is not None:
            raise self.raise_on_add
        return self.add_result_id

    def start_workflow(self, template_id: int, document_type: list) -> dict:
        self.workflow_calls.append((int(template_id), list(document_type)))
        if self.raise_on_workflow is not None:
            raise self.raise_on_workflow
        # Запомнить что для этой компании workflow стартовал — следующий
        # list_company_requisites вернёт post_workflow данные.
        doc_id = document_type[-1] if document_type else ""
        if doc_id.startswith("COMPANY_"):
            self._workflow_started.add(doc_id[len("COMPANY_"):])
        return dict(self.workflow_result)


class FakeSheets:
    def __init__(self, rows: list[QueueRow]):
        self._rows = [r.to_sheet_row() for r in rows]
        self.extra_tabs: dict[str, list[list[str]]] = {}
        self.updates: list[tuple[str, str, list[list[str]]]] = []
        self.appends: list[tuple[str, list[list[str]]]] = []
        self.ensure_calls: list[str] = []

    def read(self, sheet: str, *args, **kwargs):
        if sheet == TAB_QUEUE:
            return [QUEUE_HEADERS, *self._rows]
        return self.extra_tabs.get(sheet, [])

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs):
        self.updates.append((sheet, range_, rows))
        if sheet == TAB_QUEUE and range_.startswith("A") and ":" in range_:
            n = int(range_.split(":")[0][1:])
            idx = n - 2
            if 0 <= idx < len(self._rows):
                self._rows[idx] = rows[0]
        else:
            grid = self.extra_tabs.setdefault(sheet, [])
            if range_ == "A1":
                if not grid:
                    grid.append(rows[0])
                else:
                    grid[0] = rows[0]

    def append(self, sheet: str, rows: list[list[str]], **kwargs):
        self.appends.append((sheet, rows))
        grid = self.extra_tabs.setdefault(sheet, [])
        grid.extend(rows)

    def ensure_sheet(self, title: str, *args, **kwargs):
        self.ensure_calls.append(title)
        self.extra_tabs.setdefault(title, [])

    def batch_update(self, data, **kwargs):
        for entry in data:
            range_ = entry["range"].split("!", 1)[-1]
            self.update(TAB_QUEUE, range_, entry["values"])

    def clear(self, *args, **kwargs):
        pass

    def queue_row(self, idx: int = 0) -> QueueRow:
        return QueueRow.from_sheet_row(self._rows[idx], QUEUE_HEADERS)


@pytest.fixture
def no_sleep(monkeypatch):
    """Замокать time.sleep в модуле apply — тесты не должны висеть 15s."""
    monkeypatch.setattr("crm_company_enrich.stages.apply.time.sleep", lambda *a, **k: None)


def _approved_row(cid: str = "10", inn: str = "7707083893") -> QueueRow:
    return QueueRow(
        company_id=cid,
        company_name=f"Bitrix-title {cid}",
        discovered_inn=inn,
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPROVED,
        approved=True,
    )


# =========================================================================
# 1. Happy path — touch + BP + verify=enriched → APPLIED
# =========================================================================


def test_hybrid_happy_path_touch_bp_verify_enriched(no_sleep):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        post_workflow_requisites={
            "10": [
                {"ID": "300", "RQ_INN": "7707083893", "RQ_OGRN": ""},  # наш
                {"ID": "301", "RQ_INN": "7707083893", "RQ_OGRN": "1027700132195"},  # BP
            ]
        },
        company_data={"10": {"ID": "10", "COMMENTS": "test"}},
        workflow_result={"workflow_id": "wf-555"},
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=10,
        company_touch=True,
    )

    # add вызван
    assert len(bx.add_calls) == 1
    # touch вызван: сначала get_company, потом update_company с COMMENTS+marker.
    # Bitrix-сервер обрезает trailing whitespace — используем newline+uuid маркер.
    assert bx.get_company_calls == ["10"]
    assert len(bx.update_company_calls) == 1
    assert bx.update_company_calls[0][0] == "10"
    sent_comments = bx.update_company_calls[0][1]["COMMENTS"]
    assert sent_comments.startswith("test\n[touch "), f"expected newline marker, got {sent_comments!r}"
    assert sent_comments.endswith("]")
    assert len(sent_comments) > len("test")  # реально расширено
    # workflow стартовал
    assert len(bx.workflow_calls) == 1
    assert bx.workflow_calls[0] == (5614, ["crm", "CCrmDocumentCompany", "COMPANY_10"])
    # verify: list_company_requisites вызван ПОСЛЕ workflow (имитация BP подтянул OGRN)

    assert summary["applied"] == 1
    assert summary["applied_pending_bp"] == 0
    assert summary["verify"]["enriched"] == 1
    assert summary["verify"]["not_enriched"] == 0

    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED
    assert "wf_id=wf-555" in (updated.error_message or "")
    assert "verify=enriched(req=301)" in (updated.error_message or "")

    # backup-таб содержит bp_workflow_id и enriched_requisite_id
    grid = sheets.extra_tabs[TAB_BACKUP]
    assert grid[0] == BACKUP_HEADERS
    data_row = grid[1]
    # bp_workflow_id (column 7), bp_verify_enriched (8), enriched_requisite_id (9)
    assert data_row[7] == "wf-555"
    assert data_row[8] == "true"
    assert data_row[9] == "301"


# =========================================================================
# 2. BP запустился, verify=not_enriched → APPLIED_PENDING_BP
# =========================================================================


def test_hybrid_bp_triggered_but_verify_not_enriched_marks_pending(no_sleep):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        # после workflow всё ещё только наш реквизит (без OGRN)
        post_workflow_requisites={
            "10": [{"ID": "300", "RQ_INN": "7707083893", "RQ_OGRN": ""}]
        },
        company_data={"10": {"COMMENTS": ""}},
        workflow_result={"workflow_id": "wf-666"},
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=10,
        company_touch=True,
    )

    assert summary["applied"] == 0
    assert summary["applied_pending_bp"] == 1
    assert summary["verify"]["enriched"] == 0
    assert summary["verify"]["not_enriched"] == 1

    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED_PENDING_BP
    assert "verify=not_enriched" in (updated.error_message or "")

    grid = sheets.extra_tabs[TAB_BACKUP]
    data_row = grid[1]
    assert data_row[5] == "APPLIED_PENDING_BP"
    assert data_row[7] == "wf-666"
    assert data_row[8] == "false"
    assert data_row[9] == ""  # нет enriched_requisite_id


# =========================================================================
# 3. BP disabled — нет touch/BP/verify
# =========================================================================


def test_hybrid_bizproc_disabled_skips_touch_and_verify(no_sleep):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        company_data={"10": {"COMMENTS": ""}},
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=None,
        bizproc_wait_s=10,
        company_touch=True,  # даже если включён, всё равно делаем — это independent
    )

    assert summary["applied"] == 1
    assert summary["applied_pending_bp"] == 0
    assert summary["bizproc"]["not_configured"] == 1
    assert summary["bizproc"]["triggered"] == 0
    # workflow не вызывался
    assert bx.workflow_calls == []
    # verify не делался (BP не стартовал) — list_calls только для race-guard перед add
    assert bx.list_calls == ["10"]
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED


# =========================================================================
# 4. BP failed → APPLIED, no verify
# =========================================================================


def test_hybrid_bp_failure_still_applied_no_verify(no_sleep):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        company_data={"10": {"COMMENTS": ""}},
        raise_on_workflow=BitrixError("ACCESS_DENIED to bizproc"),
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=10,
        company_touch=True,
    )

    assert summary["applied"] == 1
    assert summary["applied_pending_bp"] == 0
    assert summary["bizproc"]["failed"] == 1
    assert summary["verify"]["enriched"] == 0
    assert summary["verify"]["not_enriched"] == 0
    # touch всё равно вызвался (он до BP)
    assert len(bx.update_company_calls) == 1
    # workflow вызвался один раз, но failed
    assert len(bx.workflow_calls) == 1
    # verify не вызывался → list_company_requisites только race-guard перед add
    assert bx.list_calls == ["10"]
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED
    assert "bizproc=failed" in (updated.error_message or "")


# =========================================================================
# 5. CCE_COMPANY_TOUCH=False — нет update_company
# =========================================================================


def test_hybrid_touch_disabled_skips_update_company(no_sleep):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        post_workflow_requisites={
            "10": [{"ID": "301", "RQ_INN": "7707083893", "RQ_OGRN": "1027700132195"}]
        },
        workflow_result={"workflow_id": "wf-no-touch"},
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=10,
        company_touch=False,
    )

    # touch отключён
    assert bx.update_company_calls == []
    assert bx.get_company_calls == []
    # но BP всё равно запустился
    assert len(bx.workflow_calls) == 1
    # verify прошёл успешно
    assert summary["applied"] == 1
    assert summary["verify"]["enriched"] == 1


# =========================================================================
# 6. dry-run — ни touch ни BP не вызываются, status не меняется
# =========================================================================


def test_hybrid_dry_run_does_not_touch_or_trigger_bp(no_sleep, capsys):
    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        company_data={"10": {"COMMENTS": ""}},
    )
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        dry_run=True,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=10,
        company_touch=True,
    )
    captured = capsys.readouterr()

    assert bx.add_calls == []
    assert bx.update_company_calls == []
    assert bx.workflow_calls == []
    assert summary["applied"] == 0
    assert summary["applied_pending_bp"] == 0
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPROVED
    assert "DRY-RUN" in captured.out


# =========================================================================
# 7. time.sleep замокан — тест не должен висеть 15s
# =========================================================================


def test_hybrid_sleep_is_mocked_during_test_run(no_sleep):
    """Sanity: после старта workflow apply делает time.sleep(wait_s).
    Если бы monkeypatch не сработал — тест занял бы 30s+.
    """
    import time as _time

    row = _approved_row(cid="10")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        post_workflow_requisites={
            "10": [{"ID": "301", "RQ_INN": "7707083893", "RQ_OGRN": "1027700132195"}]
        },
    )
    sheets = FakeSheets([row])

    started = _time.monotonic()
    apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=30,  # без мока висели бы 30с
        company_touch=False,
    )
    elapsed = _time.monotonic() - started
    assert elapsed < 2, f"apply with mocked sleep took {elapsed}s (sleep not mocked)"


# =========================================================================
# 8. APPLIED_PENDING_BP — terminal для apply (idempotency)
# =========================================================================


def test_apply_skips_applied_pending_bp_as_terminal(no_sleep):
    row = _approved_row(cid="10")
    row.status = Status.APPLIED_PENDING_BP
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets,
        sleep_s=0,
        bizproc_template_id=5614,
        bizproc_wait_s=0,
    )

    assert summary["applied"] == 0
    assert summary["applied_pending_bp"] == 0
    assert bx.add_calls == []
    assert bx.workflow_calls == []
