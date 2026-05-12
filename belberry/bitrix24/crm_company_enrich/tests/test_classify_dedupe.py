"""Тесты classify-стадии: CREATE_REQ vs MERGE_INTO vs SKIP_ALREADY."""
from __future__ import annotations

from crm_company_enrich.models import TargetAction
from crm_company_enrich.stages.classify import _decide


def test_decide_create_req_when_no_matches():
    action, target = _decide(company_id="10", matches=[])
    assert action == TargetAction.CREATE_REQ
    assert target is None


def test_decide_skip_already_when_same_owner():
    matches = [{"ID": "100", "ENTITY_ID": "10", "RQ_INN": "7707083893"}]
    action, target = _decide(company_id="10", matches=matches)
    assert action == TargetAction.SKIP_ALREADY
    assert target is None


def test_decide_merge_into_when_other_owner():
    matches = [{"ID": "100", "ENTITY_ID": "999", "RQ_INN": "7707083893"}]
    action, target = _decide(company_id="10", matches=matches)
    assert action == TargetAction.MERGE_INTO
    assert target == "999"


def test_decide_skip_already_takes_priority_over_others():
    """Если среди матчей есть и наша, и чужая компания — это SKIP_ALREADY (no-op)."""
    matches = [
        {"ID": "100", "ENTITY_ID": "999", "RQ_INN": "7707083893"},
        {"ID": "101", "ENTITY_ID": "10", "RQ_INN": "7707083893"},
    ]
    action, target = _decide(company_id="10", matches=matches)
    assert action == TargetAction.SKIP_ALREADY


def test_decide_merge_into_picks_first_other_when_multiple():
    matches = [
        {"ID": "100", "ENTITY_ID": "777", "RQ_INN": "7707083893"},
        {"ID": "101", "ENTITY_ID": "888", "RQ_INN": "7707083893"},
    ]
    action, target = _decide(company_id="10", matches=matches)
    assert action == TargetAction.MERGE_INTO
    assert target == "777"


# ----- Integration-style: classify.run with FakeBitrix + FakeSheets -----

from crm_company_enrich.models import QUEUE_HEADERS, QueueRow
from crm_company_enrich.state import Status
from crm_company_enrich.config import TAB_QUEUE
from crm_company_enrich.stages import classify


class FakeBitrix:
    """Только search_requisite_by_inn. Никаких других методов не зовётся."""

    def __init__(self, inn_to_matches: dict[str, list[dict]]):
        self.inn_to_matches = inn_to_matches
        self.calls: list[str] = []

    def search_requisite_by_inn(self, inn: str):
        self.calls.append(inn)
        return self.inn_to_matches.get(inn, [])


class FakeSheets:
    def __init__(self, rows: list[QueueRow]):
        self._rows = [r.to_sheet_row() for r in rows]
        self.updates: list[tuple[str, list[list[str]]]] = []
        self.appends: list[tuple[str, list[list[str]]]] = []
        self.ensure_calls: list[str] = []

    def read(self, sheet: str, *args, **kwargs):
        if sheet == TAB_QUEUE:
            return [QUEUE_HEADERS, *self._rows]
        return []

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs):
        # запоминаем обновление и применяем к локальной копии
        self.updates.append((range_, rows))
        # parse "A{n}:T{n}" → index
        if range_.startswith("A") and ":" in range_:
            n = int(range_.split(":")[0][1:])
            idx = n - 2
            if 0 <= idx < len(self._rows):
                self._rows[idx] = rows[0]

    def append(self, sheet: str, rows: list[list[str]], **kwargs):
        self.appends.append((sheet, rows))

    def ensure_sheet(self, title: str, *args, **kwargs):
        self.ensure_calls.append(title)

    def batch_update(self, data, **kwargs):
        for entry in data:
            range_ = entry["range"].split("!", 1)[-1]
            self.update(TAB_QUEUE, range_, entry["values"])

    def clear(self, *args, **kwargs):
        pass


def _enriched_row(cid: str, inn: str | None, in_merge: bool = False) -> QueueRow:
    return QueueRow(
        company_id=cid,
        company_name=f"Company {cid}",
        discovered_inn=inn,
        status=Status.ENRICHED,
        in_active_deal_merge=in_merge,
    )


def test_classify_run_marks_create_req(capsys):
    rows = [_enriched_row("10", "7707083893")]
    bx = FakeBitrix(inn_to_matches={"7707083893": []})
    sheets = FakeSheets(rows)

    summary = classify.run(bx, sheets)

    assert summary["create_req"] == 1
    assert summary["merge_into"] == 0
    assert bx.calls == ["7707083893"]


def test_classify_run_marks_merge_into():
    rows = [_enriched_row("10", "7707083893")]
    bx = FakeBitrix(inn_to_matches={"7707083893": [{"ENTITY_ID": "888"}]})
    sheets = FakeSheets(rows)

    summary = classify.run(bx, sheets)
    assert summary["merge_into"] == 1


def test_classify_run_marks_skip_already_when_same_company():
    rows = [_enriched_row("10", "7707083893")]
    bx = FakeBitrix(inn_to_matches={"7707083893": [{"ENTITY_ID": "10"}]})
    sheets = FakeSheets(rows)

    summary = classify.run(bx, sheets)
    assert summary["skip_already"] == 1


def test_classify_skips_already_classified_rows():
    row = _enriched_row("10", "7707083893")
    row.status = Status.CLASSIFIED  # already past
    bx = FakeBitrix(inn_to_matches={})
    sheets = FakeSheets([row])

    summary = classify.run(bx, sheets)
    assert summary["classified"] == 0
    assert bx.calls == []  # никаких Bitrix-вызовов для уже обработанной строки
