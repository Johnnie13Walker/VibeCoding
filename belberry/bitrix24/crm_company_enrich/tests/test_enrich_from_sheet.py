from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from crm_company_enrich.stages import enrich_from_sheet
from crm_company_enrich.stages.enrich_company_full import FullEnrichmentOutcome, StepOutcome

MSK = ZoneInfo("Europe/Moscow")


class FakeSheets:
    def __init__(self):
        self.sheet_id = "source"
        self.data: dict[tuple[str, str], list[list]] = {}
        self.appended: list[tuple[str, str, list[list]]] = []
        self.updated: list[tuple[str, str, str, list[list]]] = []
        self.created: list[tuple[str, str]] = []
        self.titles: set[str] = set()

    def read(self, sheet: str, range_: str = "A1:Z10000", unformatted: bool = False):
        return self.data.get((self.sheet_id, sheet), [])

    def append(self, sheet: str, rows: list[list], value_input_option: str = "RAW") -> None:
        self.appended.append((self.sheet_id, sheet, rows))
        self.data.setdefault((self.sheet_id, sheet), []).extend(rows)

    def update(self, sheet: str, range_: str, rows: list[list], value_input_option: str = "RAW") -> None:
        self.updated.append((self.sheet_id, sheet, range_, rows))
        self.data[(self.sheet_id, sheet)] = rows

    def ensure_sheet(self, title: str) -> int:
        self.titles.add(title)
        return len(self.titles)

    def create_spreadsheet(self, title: str, share_with: str) -> str:
        self.created.append((title, share_with))
        return "auto_sheet"


class FakeBitrix:
    def __init__(self, companies: list[dict] | None = None):
        self.companies = companies or []
        self.filters: list[dict] = []
        self.write_calls: list[str] = []

    def list_companies(self, select=None, filter_=None):
        self.filters.append(filter_ or {})
        return self.companies

    def call(self, method: str, params: dict | None = None):
        if method.endswith(".add") or method.endswith(".update") or method.endswith(".delete"):
            self.write_calls.append(method)
        return {"result": []}


def _full(company_id: str, status: str = "ENRICHED") -> FullEnrichmentOutcome:
    return FullEnrichmentOutcome(
        input_kind="company_id",
        input_value=company_id,
        company_id=company_id,
        deal_id=f"d{company_id}",
        duplicate_company_ids=["9"],
        flags=["skip_bp"],
        steps=[StepOutcome("RESOLVE", "DONE", {"title": f"Компания {company_id}"})],
        final_status=status,
        bitrix_links={
            "company": f"https://example.test/company/{company_id}",
            "deal": f"https://example.test/deal/{company_id}",
        },
    )


def test_load_from_file_strips_whitespace_and_skips_blanks(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("\n 17658 \n\n 17318\n", encoding="utf-8")

    inputs = enrich_from_sheet.load_inputs_from_file(path)

    assert [inp.company_id for inp in inputs] == ["17658", "17318"]
    assert inputs[0].source_row_ref.endswith(":2")


def test_load_from_file_supports_company_id_inn_url_lines(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("17658\n7707083893\nhttps://example.ru\n", encoding="utf-8")

    inputs = enrich_from_sheet.load_inputs_from_file(path)

    assert inputs[0].company_id == "17658"
    assert inputs[1].inn == "7707083893"
    assert inputs[2].url == "https://example.ru"


def test_load_from_sheet_picks_correct_column():
    sheets = FakeSheets()
    sheets.data[("sheet1", "Компании")] = [
        ["name", "crm_id"],
        ["a", "17658"],
        ["b", "17318"],
    ]

    inputs = enrich_from_sheet.load_inputs_from_sheet(sheets, "sheet1", "Компании", "crm_id")

    assert [inp.company_id for inp in inputs] == ["17658", "17318"]
    assert inputs[1].source_row_ref == "sheet:sheet1:Компании:3"
    assert sheets.sheet_id == "source"


def test_load_from_bitrix_filter_calls_company_list_with_filter():
    bx = FakeBitrix([{"ID": "1"}, {"ID": "2"}])

    inputs = enrich_from_sheet.load_inputs_from_bitrix_filter(bx, {"UF_CRM_REGION_RF": ""})

    assert [inp.company_id for inp in inputs] == ["1", "2"]
    assert bx.filters == [{"UF_CRM_REGION_RF": ""}]


def test_dedup_by_company_id_priority():
    inputs = [
        enrich_from_sheet.BatchInput(company_id="1", inn="7707083893", source_row_ref="a"),
        enrich_from_sheet.BatchInput(company_id="1", inn="7707083894", source_row_ref="b"),
    ]

    result = enrich_from_sheet.deduplicate_inputs(inputs)

    assert len(result) == 1
    assert result[0].source_row_ref == "a"


def test_dedup_by_inn_when_no_id():
    inputs = [
        enrich_from_sheet.BatchInput(inn="7707083893", source_row_ref="a"),
        enrich_from_sheet.BatchInput(inn=" 7707083893 ", source_row_ref="b"),
    ]

    result = enrich_from_sheet.deduplicate_inputs(inputs)

    assert len(result) == 1


def test_dedup_keeps_first_source_row_ref():
    inputs = [
        enrich_from_sheet.BatchInput(url="https://Example.ru/", source_row_ref="first"),
        enrich_from_sheet.BatchInput(url="http://example.ru", source_row_ref="second"),
    ]

    result = enrich_from_sheet.deduplicate_inputs(inputs)

    assert result[0].source_row_ref == "first"


def test_is_within_window_true_at_01_00_MSK():
    assert enrich_from_sheet.is_within_window(datetime(2026, 5, 17, 1, 0, tzinfo=MSK))


def test_is_within_window_false_at_09_00_MSK():
    assert not enrich_from_sheet.is_within_window(datetime(2026, 5, 17, 9, 0, tzinfo=MSK))


def test_determine_skip_bp_false_inside_window():
    assert not enrich_from_sheet.determine_skip_bp(datetime(2026, 5, 17, 1, 0, tzinfo=MSK), None, False)


def test_determine_skip_bp_true_outside_window():
    assert enrich_from_sheet.determine_skip_bp(datetime(2026, 5, 17, 9, 0, tzinfo=MSK), None, False)


def test_explicit_skip_bp_overrides_window():
    assert enrich_from_sheet.determine_skip_bp(datetime(2026, 5, 17, 1, 0, tzinfo=MSK), True, False)


def test_explicit_full_bp_overrides_window():
    assert not enrich_from_sheet.determine_skip_bp(datetime(2026, 5, 17, 9, 0, tzinfo=MSK), None, True)


def test_should_stop_by_window_in_cron_mode():
    start = datetime(2026, 5, 17, 1, 0, tzinfo=MSK)
    now = datetime(2026, 5, 17, 8, 0, tzinfo=MSK)

    assert enrich_from_sheet.should_stop(start, 480, now_msk=now, cron_mode=True)


def test_run_dry_run_does_not_call_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich_from_sheet, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(enrich_from_sheet.enrich_company_full, "run", lambda bx, **kwargs: _full(kwargs["company_id"]))
    bx = FakeBitrix()
    sheets = FakeSheets()

    summary = enrich_from_sheet.run(
        bx,
        sheets,
        inputs=[enrich_from_sheet.BatchInput(company_id="1", source_row_ref="file:x:1")],
        output_sheet_id="out",
        output_tab="results",
        dry_run=True,
        skip_bp=True,
    )

    assert summary["processed"] == 1
    assert bx.write_calls == []


def test_run_cron_mode_exits_early_if_outside_window(monkeypatch, tmp_path):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 17, 9, 0, tzinfo=MSK)

    monkeypatch.setattr(enrich_from_sheet, "datetime", FakeDateTime)
    monkeypatch.setattr(enrich_from_sheet, "STATE_PATH", tmp_path / "state.json")

    summary = enrich_from_sheet.run(
        FakeBitrix(),
        FakeSheets(),
        inputs=[enrich_from_sheet.BatchInput(company_id="1")],
        output_sheet_id="out",
        output_tab="results",
        cron_mode=True,
    )

    assert summary["processed"] == 0
    assert summary["stopped_by_window"] == 1


def test_run_stops_when_max_duration_exceeded(monkeypatch, tmp_path):
    class FakeDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            if cls.calls == 1:
                return datetime(2026, 5, 17, 1, 0, tzinfo=MSK)
            return datetime(2026, 5, 17, 1, 2, tzinfo=MSK)

    monkeypatch.setattr(enrich_from_sheet, "datetime", FakeDateTime)
    monkeypatch.setattr(enrich_from_sheet, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(enrich_from_sheet.enrich_company_full, "run", lambda bx, **kwargs: _full(kwargs["company_id"]))

    summary = enrich_from_sheet.run(
        FakeBitrix(),
        FakeSheets(),
        inputs=[enrich_from_sheet.BatchInput(company_id="1")],
        output_sheet_id="out",
        output_tab="results",
        max_duration_min=1,
    )

    assert summary["processed"] == 0
    assert summary["stopped_by_duration"] == 1


def test_run_appends_output_row_per_company(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich_from_sheet, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(enrich_from_sheet.enrich_company_full, "run", lambda bx, **kwargs: _full(kwargs["company_id"]))
    sheets = FakeSheets()

    summary = enrich_from_sheet.run(
        FakeBitrix(),
        sheets,
        inputs=[
            enrich_from_sheet.BatchInput(company_id="1"),
            enrich_from_sheet.BatchInput(company_id="2"),
        ],
        output_sheet_id="out",
        output_tab="results",
        skip_bp=True,
    )

    assert summary["processed"] == 2
    assert len([item for item in sheets.appended if item[1] == "results"]) == 2


def test_run_handles_exception_gracefully(monkeypatch, tmp_path):
    def fake_run(bx, **kwargs):
        if kwargs["company_id"] == "bad":
            raise RuntimeError("boom")
        return _full(kwargs["company_id"])

    monkeypatch.setattr(enrich_from_sheet, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(enrich_from_sheet.enrich_company_full, "run", fake_run)
    sheets = FakeSheets()

    summary = enrich_from_sheet.run(
        FakeBitrix(),
        sheets,
        inputs=[
            enrich_from_sheet.BatchInput(company_id="ok"),
            enrich_from_sheet.BatchInput(company_id="bad"),
            enrich_from_sheet.BatchInput(company_id="after"),
        ],
        output_sheet_id="out",
        output_tab="results",
        skip_bp=True,
    )

    assert summary["processed"] == 3
    assert summary["failed"] == 1
    assert summary["status_counts"]["EXCEPTION"] == 1
