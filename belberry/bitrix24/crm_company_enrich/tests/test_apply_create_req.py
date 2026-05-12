"""Offline unit-тесты apply-стадии для target_action=CREATE_REQ.

Использует FakeBitrix + FakeSheets. Никаких сетевых вызовов.

Покрытие (см. README write-стадии):
  1. Happy path CREATE_REQ — add_requisite вызван 1 раз, status=APPLIED.
  2. Race-condition guard — компания уже имеет валидный реквизит → SKIPPED.
  3. Invalid INN → FAILED.
  4. in_active_deal_merge=1 → FAILED + no add call.
  5. MERGE_INTO — пропускается без изменения статуса.
  6. SKIP_ALREADY → SKIPPED.
  7. --dry-run → status не меняется, нет add-вызовов.
  8. Bizproc not_configured (template_id=None).
  9. Bizproc triggered (template_id=42).
 10. Idempotency — повторный запуск пропускает APPLIED строки.
 11. Backup-таб: header + строка на каждую попытку (включая FAILED).
"""
from __future__ import annotations

from crm_company_enrich.config import TAB_BACKUP, TAB_QUEUE
from crm_company_enrich.models import QUEUE_HEADERS, QueueRow, TargetAction
from crm_company_enrich.stages import apply
from crm_company_enrich.stages.apply import BACKUP_HEADERS
from crm_company_enrich.state import Status


# ----- Fakes -----


class FakeBitrix:
    """Перехватывает list_company_requisites / add_requisite / start_workflow.

    add_result_id — что вернёт add_requisite (если не raise).
    raise_on_add — Exception, который add_requisite кинет (для негативных тестов).
    """

    def __init__(
        self,
        existing_requisites: dict[str, list[dict]] | None = None,
        add_result_id: str = "12345",
        raise_on_add: Exception | None = None,
        workflow_result: dict | None = None,
        raise_on_workflow: Exception | None = None,
    ):
        self.existing = existing_requisites or {}
        self.add_result_id = add_result_id
        self.raise_on_add = raise_on_add
        self.workflow_result = workflow_result or {"workflow_id": "wf-777"}
        self.raise_on_workflow = raise_on_workflow

        self.add_calls: list[dict] = []
        self.list_calls: list[str] = []
        self.workflow_calls: list[tuple[int, list]] = []

    def list_company_requisites(self, company_id: str) -> list[dict]:
        self.list_calls.append(str(company_id))
        return list(self.existing.get(str(company_id), []))

    def add_requisite(self, fields: dict) -> str:
        self.add_calls.append(dict(fields))
        if self.raise_on_add is not None:
            raise self.raise_on_add
        return self.add_result_id

    def start_workflow(self, template_id: int, document_type: list) -> dict:
        self.workflow_calls.append((int(template_id), list(document_type)))
        if self.raise_on_workflow is not None:
            raise self.raise_on_workflow
        return dict(self.workflow_result)


class FakeSheets:
    """Хранит queue-таб + произвольные «дополнительные» табы (backup и т.д.)."""

    def __init__(self, rows: list[QueueRow]):
        self._rows = [r.to_sheet_row() for r in rows]
        self.extra_tabs: dict[str, list[list[str]]] = {}  # name → grid

        self.updates: list[tuple[str, str, list[list[str]]]] = []
        self.appends: list[tuple[str, list[list[str]]]] = []
        self.ensure_calls: list[str] = []

    # ----- queue helpers -----

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
            # Запись заголовков backup-таба в A1
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

    # ----- introspection -----

    def queue_row(self, idx: int = 0) -> QueueRow:
        """Достать current QueueRow из локального backing-store."""
        return QueueRow.from_sheet_row(self._rows[idx], QUEUE_HEADERS)


# ----- factory -----


def _approved_create_req(
    cid: str = "10",
    inn: str = "7707083893",
    discovered_name: str | None = "ООО Тест",
    discovered_source: str | None = "rusprofile",
    in_merge: bool = False,
    approved: bool = True,
) -> QueueRow:
    return QueueRow(
        company_id=cid,
        company_name=f"Bitrix-title {cid}",
        discovered_inn=inn,
        discovered_name=discovered_name,
        discovered_source=discovered_source,
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPROVED,
        in_active_deal_merge=in_merge,
        approved=approved,
    )


# =========================================================================
# 1. Happy path
# =========================================================================


def test_happy_path_create_req_calls_add_and_sets_applied():
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["applied"] == 1
    assert summary["failed"] == 0
    assert len(bx.add_calls) == 1
    payload = bx.add_calls[0]
    assert payload["ENTITY_TYPE_ID"] == 4
    assert payload["ENTITY_ID"] == 10
    assert payload["RQ_INN"] == "7707083893"
    assert payload["PRESET_ID"] == 1
    # 10-значный ИНН + discovered_name из rusprofile → используем discovered_name
    assert payload["RQ_COMPANY_NAME_FULL"] == "ООО Тест"

    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED
    assert "requisite_id=12345" in (updated.error_message or "")


# =========================================================================
# 2. Race-condition guard
# =========================================================================


def test_race_condition_guard_skips_when_already_has_valid_requisite():
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(
        existing_requisites={"10": [{"ID": "999", "RQ_INN": "7707083893"}]}
    )
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["skipped_already_has_requisite"] == 1
    assert summary["applied"] == 0
    assert bx.add_calls == []  # никакого write
    updated = sheets.queue_row(0)
    assert updated.status == Status.SKIPPED
    assert "already has" in (updated.error_message or "")


# =========================================================================
# 3. Invalid INN
# =========================================================================


def test_invalid_inn_fails_without_call():
    row = _approved_create_req(cid="10", inn="abc123")  # невалидный
    row.discovered_inn = "abc123"  # бывает легаси-данные «грязные»
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["failed"] == 1
    assert summary["applied"] == 0
    assert bx.add_calls == []
    updated = sheets.queue_row(0)
    assert updated.status == Status.FAILED
    assert "invalid inn" in (updated.error_message or "").lower()


# =========================================================================
# 4. in_active_deal_merge=1
# =========================================================================


def test_in_active_deal_merge_marks_failed_and_skips_call():
    row = _approved_create_req(cid="10", in_merge=True)
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["skipped_active_merge"] == 1
    assert bx.add_calls == []
    updated = sheets.queue_row(0)
    assert updated.status == Status.FAILED
    assert "active deal-merge" in (updated.error_message or "")


# =========================================================================
# 5. MERGE_INTO is skipped without status change
# =========================================================================


def test_merge_into_skipped_without_call_or_status_change(capsys):
    row = _approved_create_req(cid="10")
    row.target_action = TargetAction.MERGE_INTO
    row.merge_target_company_id = "999"
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    captured = capsys.readouterr()

    assert summary["skipped_other_action"] == 1
    assert summary["applied"] == 0
    assert bx.add_calls == []
    # Статус НЕ меняется — остаётся APPROVED для будущего merge_dupes
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPROVED
    assert "merge_dupes not implemented" in captured.out


# =========================================================================
# 6. SKIP_ALREADY
# =========================================================================


def test_skip_already_marks_skipped_without_call():
    row = _approved_create_req(cid="10")
    row.target_action = TargetAction.SKIP_ALREADY
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert bx.add_calls == []
    assert summary["applied"] == 0
    # SKIP_ALREADY обработана и зафиксирована в SKIPPED — в other_action
    # не попадает (это нормальный путь, не «незнакомый action»).
    updated = sheets.queue_row(0)
    assert updated.status == Status.SKIPPED


# =========================================================================
# 7. --dry-run
# =========================================================================


def test_dry_run_does_not_call_add_or_change_status(capsys):
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(
        bx,
        sheets,
        dry_run=True,
        sleep_s=0,
        bizproc_template_id=42,  # дoлжен ИГНОРироваться в dry-run
    )
    captured = capsys.readouterr()

    assert bx.add_calls == []
    assert bx.workflow_calls == []
    assert summary["applied"] == 0
    # backup-таб НЕ создаётся в dry-run
    assert TAB_BACKUP not in sheets.ensure_calls
    # ни одного append-вызова в backup
    backup_appends = [a for a in sheets.appends if a[0] == TAB_BACKUP]
    assert backup_appends == []
    # Статус НЕ меняется на APPLIED
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPROVED
    assert "DRY-RUN" in captured.out
    assert "would call" in captured.out


# =========================================================================
# 8. Bizproc not configured
# =========================================================================


def test_bizproc_not_configured_records_status():
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["bizproc"]["not_configured"] == 1
    assert summary["bizproc"]["triggered"] == 0
    assert bx.workflow_calls == []  # bizproc.workflow.start не вызывался
    updated = sheets.queue_row(0)
    assert "bizproc=not_configured" in (updated.error_message or "")


# =========================================================================
# 9. Bizproc triggered
# =========================================================================


def test_bizproc_triggered_writes_workflow_id():
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        workflow_result={"workflow_id": "wf-777"},
    )
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=42)

    assert summary["bizproc"]["triggered"] == 1
    assert len(bx.workflow_calls) == 1
    template_id, doc_type = bx.workflow_calls[0]
    assert template_id == 42
    assert doc_type == ["crm", "CCrmDocumentCompany", "COMPANY_10"]
    updated = sheets.queue_row(0)
    assert "bizproc=triggered: wf-777" in (updated.error_message or "")


def test_bizproc_failure_is_recorded_but_does_not_fail_apply():
    """bizproc упал → apply всё равно APPLIED, bizproc_status=failed."""
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        raise_on_workflow=RuntimeError("bizproc 403"),
    )
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=42)

    assert summary["applied"] == 1
    assert summary["bizproc"]["failed"] == 1
    updated = sheets.queue_row(0)
    assert updated.status == Status.APPLIED
    assert "bizproc=failed: bizproc 403" in (updated.error_message or "")


# =========================================================================
# 10. Idempotency
# =========================================================================


def test_idempotency_skips_already_applied_rows():
    row = _approved_create_req(cid="10", inn="7707083893")
    row.status = Status.APPLIED  # уже обработана прошлым запуском
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["applied"] == 0
    assert bx.add_calls == []
    assert bx.list_calls == []  # даже race-guard не дёргался


def test_idempotency_skips_failed_rows():
    """FAILED тоже terminal — повторный apply их не трогает (требует rollback)."""
    row = _approved_create_req(cid="10", inn="7707083893")
    row.status = Status.FAILED
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    assert summary["applied"] == 0
    assert bx.add_calls == []


# =========================================================================
# 11. Backup tab
# =========================================================================


def test_backup_tab_created_with_headers_on_first_write():
    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert TAB_BACKUP in sheets.ensure_calls
    grid = sheets.extra_tabs[TAB_BACKUP]
    # row 0 — header, row 1 — данные
    assert grid[0] == BACKUP_HEADERS
    assert len(grid) >= 2
    data_row = grid[1]
    assert data_row[1] == "10"             # company_id
    assert data_row[2] == "CREATE_REQ"     # action
    assert data_row[5] == "APPLIED"        # applied_status
    assert "7707083893" in data_row[3]     # payload_json содержит ИНН


def test_backup_records_failure_too():
    from crm_company_enrich.bitrix_client import BitrixError

    row = _approved_create_req(cid="10", inn="7707083893")
    bx = FakeBitrix(
        existing_requisites={"10": []},
        raise_on_add=BitrixError("ACCESS_DENIED"),
    )
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["failed"] == 1
    grid = sheets.extra_tabs[TAB_BACKUP]
    assert len(grid) == 2  # header + одна строка
    data_row = grid[1]
    assert data_row[5] == "FAILED"
    assert "ACCESS_DENIED" in data_row[6]


# =========================================================================
# Дополнительно: payload-логика для разных кейсов
# =========================================================================


def test_payload_uses_bitrix_title_when_no_discovered_name_for_12_digit_inn():
    """12-значный ИНН (ИП) — discovered_name пустой → берём bitrix_title."""
    row = _approved_create_req(
        cid="10",
        inn="500100732259",  # 12 цифр
        discovered_name=None,
        discovered_source="web",
    )
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    payload = bx.add_calls[0]
    assert payload["RQ_INN"] == "500100732259"
    assert payload["NAME"] == "Реквизиты ИП"
    assert payload["RQ_COMPANY_NAME_FULL"] == "Bitrix-title 10"


def test_payload_leaves_company_name_empty_for_10_digit_inn_without_discovered_name():
    """10-значный ИНН (ЮЛ) без discovered_name → НЕ ставим bitrix_title как юр-name."""
    row = _approved_create_req(
        cid="10",
        inn="7707083893",
        discovered_name=None,
        discovered_source="web",
    )
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    payload = bx.add_calls[0]
    assert "RQ_COMPANY_NAME_FULL" not in payload  # пустое — не пишем


def test_limit_respected():
    rows = [
        _approved_create_req(cid="10", inn="7707083893"),
        _approved_create_req(cid="20", inn="7728168971"),
        _approved_create_req(cid="30", inn="7710140679"),
    ]
    bx = FakeBitrix(existing_requisites={"10": [], "20": [], "30": []})
    sheets = FakeSheets(rows)

    summary = apply.run(bx, sheets, sleep_s=0, limit=2, bizproc_template_id=None)

    assert summary["applied"] == 2
    assert len(bx.add_calls) == 2
    # Третья строка осталась APPROVED
    assert QueueRow.from_sheet_row(sheets._rows[2], QUEUE_HEADERS).status == Status.APPROVED


def test_non_approved_rows_are_not_processed():
    row = _approved_create_req(cid="10", inn="7707083893")
    row.status = Status.CLASSIFIED  # не APPROVED
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    assert summary["applied"] == 0
    assert bx.add_calls == []
