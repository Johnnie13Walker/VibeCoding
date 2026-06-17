"""Тесты batch-mode для transfer (×10 speedup через Bitrix batch + Sheets batchUpdate)."""
from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.state import Status


class _BatchBitrix:
    """FakeBitrix с подсчётом batch-вызовов и sequential-вызовов."""

    def __init__(self, batch_result_override: dict | None = None):
        self.batch_calls: list[dict] = []      # каждый element = commands dict переданный в batch
        self.sequential_calls: list[tuple] = []  # tuples (method, *args)
        self.batch_result_override = batch_result_override  # для эмуляции partial failure

    def batch(self, commands: dict) -> dict:
        self.batch_calls.append(commands)
        if self.batch_result_override is not None:
            return {k: self.batch_result_override.get(k, True) for k in commands}
        return {k: True for k in commands}

    # Sequential (non-batched) методы
    def reassign_activity(self, *args, **kwargs):
        self.sequential_calls.append(("reassign_activity", args, kwargs))
        return True

    def reassign_task_activity(self, *args, **kwargs):
        self.sequential_calls.append(("reassign_task_activity", args, kwargs))
        return True

    def add_deal_timeline_comment(self, *args, **kwargs):
        self.sequential_calls.append(("add_deal_timeline_comment", args, kwargs))
        return "1"

    def add_deal_contact(self, *args, **kwargs):
        self.sequential_calls.append(("add_deal_contact", args, kwargs))
        return True

    def relink_smart_item(self, *args, **kwargs):
        self.sequential_calls.append(("relink_smart_item", args, kwargs))
        return True

    def list_deal_contacts(self, deal_id):
        return []

    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": "foo.ru", "STAGE_ID": "C50:NEW", "COMMENTS": ""}

    def update_deal(self, *args, **kwargs):
        return True


class _BatchSheets:
    """FakeSheets с подсчётом batch-update вызовов."""

    def __init__(self, rows: dict):
        self.rows = rows
        self.update_calls: list[tuple] = []
        self.batch_update_calls: list[list] = []
        self.append_calls: list[tuple] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, values, value_input_option="RAW"):
        self.update_calls.append((sheet, range_, values))

    def batch_update(self, data, value_input_option="RAW"):
        self.batch_update_calls.append(data)

    def append(self, *args, **kwargs):
        self.append_calls.append(args)

    def ensure_sheet(self, *args, **kwargs):
        pass


class _FlushTrackingSheets(_BatchSheets):
    """FakeSheets, который считает только flush-вызовы по merge_inventory."""

    def __init__(self, rows: dict, fail_inventory_flush: int | None = None, fail_once: bool = False):
        super().__init__(rows)
        self.inventory_flush_attempts = 0
        self.inventory_flush_successes: list[tuple[str, object]] = []
        self.fail_inventory_flush = fail_inventory_flush
        self.fail_once = fail_once
        self._failed_once = False

    def update(self, sheet, range_, values, value_input_option="RAW"):
        if sheet == TAB_INVENTORY:
            self._maybe_fail_inventory_flush()
            self.inventory_flush_successes.append((range_, values))
        super().update(sheet, range_, values, value_input_option=value_input_option)

    def batch_update(self, data, value_input_option="RAW"):
        if any(entry["range"].startswith(TAB_INVENTORY) for entry in data):
            self._maybe_fail_inventory_flush()
            self.inventory_flush_successes.append(("batch", data))
        super().batch_update(data, value_input_option=value_input_option)

    def _maybe_fail_inventory_flush(self):
        self.inventory_flush_attempts += 1
        if self.fail_once and not self._failed_once:
            self._failed_once = True
            raise TimeoutError("timed out")
        if self.fail_inventory_flush is not None and self.inventory_flush_attempts >= self.fail_inventory_flush:
            raise TimeoutError("timed out")


def _group(approved=True, winner_id="200"):
    return Group(
        company_id="10",
        company_name="C",
        inn="123",
        domain="foo.ru",
        winner_id=winner_id,
        winner_stage="C50:NEW",
        winner_stage_name="N",
        winner_closed=False,
        loser_ids=["100"],
        n_total=2,
        n_winner=1,
        status=Status.APPROVED,
        approved=approved,
    )


def _inventory_row(rn, entity_type, child_id, details='{}', subject="x"):
    """Создать inventory row dict — порядок колонок как в INVENTORY_HEADERS."""
    return ["10", "100", entity_type, child_id, subject, details, "0", "", ""]


def test_batch_mode_collapses_activity_calls():
    """10 non-VOXI/non-TASK активностей → 1 batch call вместо 10 sequential."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS]
    for i in range(10):
        inv.append(_inventory_row(2 + i, "activity", f"a{i}",
                                  '{"PROVIDER_ID": "CRM_EMAIL"}'))
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    result = transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # Bitrix должен получить ровно 1 batch с 10 операциями crm.activity.update
    assert len(bx.batch_calls) == 1
    assert len(bx.batch_calls[0]) == 10
    assert all("crm.activity.update" in v[0] for v in bx.batch_calls[0].values())
    # Никаких sequential reassign_activity
    assert not any(c[0] == "reassign_activity" for c in bx.sequential_calls)
    assert result["activity"] == 10


def test_batch_mode_voximplant_not_in_batch():
    """VOXIMPLANT_CALL остаётся not_transferable, не попадает в batch."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "activity", "a1", '{"PROVIDER_ID": "VOXIMPLANT_CALL"}'),
           _inventory_row(3, "activity", "a2", '{"PROVIDER_ID": "CRM_EMAIL"}')]
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # batch имеет только 1 activity (CRM_EMAIL)
    assert len(bx.batch_calls) == 1
    assert len(bx.batch_calls[0]) == 1


def test_batch_mode_tasks_remain_sequential():
    """CRM_TASKS_TASK идёт через reassign_task_activity, не batch."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "activity", "a1", '{"PROVIDER_ID": "CRM_TASKS_TASK"}'),
           _inventory_row(3, "activity", "a2", '{"PROVIDER_ID": "TASKS"}'),
           _inventory_row(4, "activity", "a3", '{"PROVIDER_ID": "CRM_EMAIL"}')]
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # 2 task через sequential
    task_calls = [c for c in bx.sequential_calls if c[0] == "reassign_task_activity"]
    assert len(task_calls) == 2
    # 1 non-task в batch
    assert len(bx.batch_calls) == 1
    assert len(bx.batch_calls[0]) == 1


def test_batch_mode_timeline_collapsed():
    """5 timeline-комментов → 1 batch call с crm.timeline.comment.add."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS]
    for i in range(5):
        inv.append(_inventory_row(2 + i, "timeline", f"t{i}", '{"COMMENT": "hi"}'))
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    assert len(bx.batch_calls) == 1
    assert len(bx.batch_calls[0]) == 5
    assert all("crm.timeline.comment.add" in v[0] for v in bx.batch_calls[0].values())


def test_batch_mode_contact_already_linked_skipped():
    """already_linked контакт не попадает в batch."""

    class _BxWithContacts(_BatchBitrix):
        def list_deal_contacts(self, deal_id):
            return [{"CONTACT_ID": "777"}]  # уже привязан

    bx = _BxWithContacts()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "contact", "777", "{}"),    # уже linked
           _inventory_row(3, "contact", "888", "{}")]    # новый
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # batch только 1 (888)
    assert len(bx.batch_calls) == 1
    assert len(bx.batch_calls[0]) == 1


def test_batch_mode_partial_failure():
    """Если batch вернул {a0: True, a1: False} → одна row transferred=1, другая 0 с note=batch_failed."""
    bx = _BatchBitrix(batch_result_override={"a0": True, "a1": False})
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "activity", "a0", '{"PROVIDER_ID": "CRM_EMAIL"}'),
           _inventory_row(3, "activity", "a1", '{"PROVIDER_ID": "CRM_EMAIL"}')]
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # Фильтруем только inventory writes (не backup-sheet writes)
    inv_writes = [(r, v) for s, r, v in sheets.update_calls if s == TAB_INVENTORY]
    for d in sheets.batch_update_calls:
        for entry in d:
            if entry["range"].startswith(TAB_INVENTORY):
                inv_writes.append((entry["range"], entry["values"]))
    all_values = []
    for _, values in inv_writes:
        all_values.extend(values)
    transferred_flags = [row[6] for row in all_values]  # колонка transferred
    notes = [row[8] for row in all_values]              # колонка note
    assert "1" in transferred_flags
    assert "0" in transferred_flags
    assert "batch_failed" in notes


def test_batch_mode_sp_remain_sequential():
    """SP идут через relink_smart_item sequential (не batch). Telemetry skipped."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "sp:1040", "x1", "{}"),    # telemetry
           _inventory_row(3, "sp:1048", "x2", "{}")]    # бизнес SP
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    # sp:1048 через sequential relink_smart_item
    sp_calls = [c for c in bx.sequential_calls if c[0] == "relink_smart_item"]
    assert len(sp_calls) == 1
    # batch_calls пусто (нет non-task activity/timeline/contact)
    assert bx.batch_calls == []


def test_sequential_mode_still_works():
    """Без --batch-mode классический путь — никаких batch вызовов."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "activity", "a1", '{"PROVIDER_ID": "CRM_EMAIL"}')]
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=False, batch_mode=False, limit=1)
    assert bx.batch_calls == []
    # Должен быть sequential reassign_activity
    seq = [c[0] for c in bx.sequential_calls]
    assert "reassign_activity" in seq


def test_dry_run_batch_no_writes():
    """--dry-run --batch-mode не вызывает write."""
    bx = _BatchBitrix()
    inv = [INVENTORY_HEADERS,
           _inventory_row(2, "activity", "a1", '{"PROVIDER_ID": "CRM_EMAIL"}')]
    sheets = _BatchSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })
    transfer.run(bx, sheets, dry_run=True, batch_mode=True, limit=1)
    assert bx.batch_calls == []
    assert bx.sequential_calls == []
    assert sheets.update_calls == []
    assert sheets.batch_update_calls == []


def test_batch_per_stage_flush():
    """Batch-mode flush'ит inventory после каждой непустой стадии."""
    bx = _BatchBitrix()
    inv = [
        INVENTORY_HEADERS,
        _inventory_row(2, "activity", "voxi", '{"PROVIDER_ID": "VOXIMPLANT_CALL"}'),
        _inventory_row(3, "activity", "task", '{"PROVIDER_ID": "CRM_TASKS_TASK"}'),
        _inventory_row(4, "activity", "mail", '{"PROVIDER_ID": "CRM_EMAIL"}'),
        _inventory_row(5, "timeline", "tl", '{"COMMENT": "hi"}'),
        _inventory_row(6, "contact", "777", "{}"),
        _inventory_row(7, "sp:1048", "340", "{}"),
    ]
    sheets = _FlushTrackingSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })

    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)

    # direct, task, activity, timeline, contact, sp — шесть независимых flush.
    assert len(sheets.inventory_flush_successes) == 6
    assert [call[0] for call in bx.sequential_calls if call[0] == "reassign_task_activity"]
    assert [call[0] for call in bx.sequential_calls if call[0] == "relink_smart_item"]


def test_batch_flush_timeout_mid_group(monkeypatch):
    """Если Sheets упал после Bitrix batch, группа уходит FAILED, а успешный flush остаётся зафиксирован."""
    monkeypatch.setattr(transfer.time, "sleep", lambda _: None)
    bx = _BatchBitrix()
    inv = [
        INVENTORY_HEADERS,
        _inventory_row(2, "activity", "mail", '{"PROVIDER_ID": "CRM_EMAIL"}'),
        _inventory_row(3, "timeline", "tl", '{"COMMENT": "hi"}'),
        _inventory_row(4, "contact", "777", "{}"),
    ]
    sheets = _FlushTrackingSheets(
        {
            TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
            TAB_INVENTORY: inv,
        },
        fail_inventory_flush=2,
    )

    result = transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)

    assert result["failed"] == 1
    assert len(sheets.inventory_flush_successes) == 1
    # activity batch и timeline batch уже были вызваны до падения второго flush.
    assert len(bx.batch_calls) == 2
    failed_group_writes = [values for sheet, _, values in sheets.update_calls if sheet == TAB_GROUPS]
    assert failed_group_writes
    assert Status.FAILED.value in failed_group_writes[-1][0]


def test_batch_flush_retry_succeeds(monkeypatch):
    """Timeout на первой попытке flush не валит группу, если retry успешен."""
    monkeypatch.setattr(transfer.time, "sleep", lambda _: None)
    bx = _BatchBitrix()
    inv = [
        INVENTORY_HEADERS,
        _inventory_row(2, "activity", "mail", '{"PROVIDER_ID": "CRM_EMAIL"}'),
    ]
    sheets = _FlushTrackingSheets(
        {
            TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
            TAB_INVENTORY: inv,
        },
        fail_once=True,
    )

    result = transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)

    assert result["groups"] == 1
    assert "failed" not in result
    assert sheets.inventory_flush_attempts == 2


def test_batch_flush_non_retryable_error_raises(monkeypatch):
    """Не-retryable ошибки Sheets не маскируются."""
    bx = _BatchBitrix()
    inv = [
        INVENTORY_HEADERS,
        _inventory_row(2, "activity", "mail", '{"PROVIDER_ID": "CRM_EMAIL"}'),
    ]

    class _BadSheets(_FlushTrackingSheets):
        def update(self, sheet, range_, values, value_input_option="RAW"):
            if sheet == TAB_INVENTORY:
                raise ValueError("bad payload")
            return super().update(sheet, range_, values, value_input_option=value_input_option)

    sheets = _BadSheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: inv,
    })

    try:
        transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)
    except ValueError as exc:
        assert "bad payload" in str(exc)
    else:
        raise AssertionError("ValueError должен пробрасываться")
