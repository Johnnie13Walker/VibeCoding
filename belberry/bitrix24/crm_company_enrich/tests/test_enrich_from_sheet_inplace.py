from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from crm_company_enrich.stages import enrich_from_sheet_inplace as stage
from crm_company_enrich.stages.enrich_company_full import FullEnrichmentOutcome, StepOutcome


MSK = ZoneInfo("Europe/Moscow")


# ---------- helpers ----------

def _grid(rows: list[list[dict]], sheet_gid: int = 1318170868) -> dict:
    return {
        "sheets": [{
            "properties": {"sheetId": sheet_gid, "title": "TestTab"},
            "data": [{"rowData": [{"values": row} for row in rows]}],
        }]
    }


def _cell(formatted: str = "", hyperlink: str = "") -> dict:
    out: dict = {}
    if formatted:
        out["formattedValue"] = formatted
    if hyperlink:
        out["hyperlink"] = hyperlink
    return out


# ---------- parse_deal_id_from_url ----------

def test_parse_deal_id_from_bitrix_url():
    assert stage.parse_deal_id_from_url(
        "https://belberrycrm.bitrix24.ru/crm/deal/details/12345/"
    ) == "12345"


def test_parse_deal_id_no_trailing_slash():
    assert stage.parse_deal_id_from_url(
        "https://belberrycrm.bitrix24.ru/crm/deal/details/777"
    ) == "777"


def test_parse_deal_id_returns_empty_when_no_match():
    assert stage.parse_deal_id_from_url("https://example.com/page") == ""
    assert stage.parse_deal_id_from_url("") == ""


# ---------- normalize_url_value ----------

def test_normalize_url_value_strips_scheme_and_slash():
    assert stage.normalize_url_value("https://Foo.RU/") == "foo.ru"
    assert stage.normalize_url_value("http://foo.ru") == "foo.ru"
    assert stage.normalize_url_value("foo.ru/") == "foo.ru"


def test_normalize_url_value_empty():
    assert stage.normalize_url_value("") == ""
    assert stage.normalize_url_value("   ") == ""


# ---------- extract_row_inputs ----------

def test_extract_row_inputs_with_hyperlink_extracts_deal_id():
    grid = _grid([
        [_cell("Сделка"), _cell("Воронка"), _cell("Ответственный"), _cell("Стадия"),
         _cell("Компания"), _cell("ИНН"), _cell("Оборот"), _cell("Reason"),
         _cell("deal_id"), _cell("enriched_at"), _cell("status")],
        [_cell("sladskaz.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/55555/"),
         _cell("Телемаркетинг"), _cell("Иван"), _cell("К обзвону"),
         _cell("sladskaz.ru"), _cell(""), _cell(""), _cell("no inn"),
         _cell(""), _cell(""), _cell("")],
    ])
    inputs = stage.extract_row_inputs(grid)
    assert len(inputs) == 1
    assert inputs[0].deal_id == "55555"
    assert inputs[0].url == ""
    assert inputs[0].row_number == 2  # header at row 1, first data at row 2
    assert inputs[0].company_title == "sladskaz.ru"
    assert inputs[0].existing_status == ""


def test_extract_row_inputs_without_hyperlink_uses_url_fallback():
    grid = _grid([
        [_cell("Сделка")] + [_cell()] * 10,
        [_cell("kankadze.school")] + [_cell()] * 10,
    ])
    inputs = stage.extract_row_inputs(grid)
    assert len(inputs) == 1
    assert inputs[0].deal_id == ""
    assert inputs[0].url == "https://kankadze.school"


def test_extract_row_inputs_skips_truly_empty_rows():
    grid = _grid([
        [_cell("Сделка")] + [_cell()] * 10,
        [_cell("foo.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/10/")] + [_cell()] * 10,
        [_cell()] * 11,  # truly empty
        [_cell("bar.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/20/")] + [_cell()] * 10,
    ])
    inputs = stage.extract_row_inputs(grid)
    assert [i.deal_id for i in inputs] == ["10", "20"]


def test_extract_row_inputs_picks_up_existing_status():
    cells = [_cell()] * 11
    cells[0] = _cell("foo.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/77/")
    cells[10] = _cell("ENRICHED")  # col K
    grid = _grid([
        [_cell("Сделка")] + [_cell()] * 10,
        cells,
    ])
    inputs = stage.extract_row_inputs(grid)
    assert len(inputs) == 1
    assert inputs[0].existing_status == "ENRICHED"


# ---------- filter_unprocessed ----------

def test_filter_unprocessed_drops_rows_with_status():
    rows = [
        stage.RowInput(row_number=2, deal_id="1", existing_status=""),
        stage.RowInput(row_number=3, deal_id="2", existing_status="ENRICHED"),
        stage.RowInput(row_number=4, deal_id="3", existing_status="FAILED"),
        stage.RowInput(row_number=5, deal_id="4", existing_status=""),
    ]
    assert [r.deal_id for r in stage.filter_unprocessed(rows)] == ["1", "4"]


# ---------- color_for_status ----------

def test_color_for_status_success_for_enriched_and_partial():
    assert stage.color_for_status("ENRICHED") == stage.COLOR_SUCCESS
    assert stage.color_for_status("PARTIAL") == stage.COLOR_SUCCESS


def test_color_for_status_failure_for_failed_rejected_exception():
    assert stage.color_for_status("FAILED") == stage.COLOR_FAILURE
    assert stage.color_for_status("REJECTED") == stage.COLOR_FAILURE
    assert stage.color_for_status("EXCEPTION") == stage.COLOR_FAILURE


def test_color_for_status_neutral_for_skipped_and_unknown():
    assert stage.color_for_status("SKIPPED") == stage.COLOR_NEUTRAL
    assert stage.color_for_status("UNKNOWN") == stage.COLOR_NEUTRAL
    assert stage.color_for_status("") == stage.COLOR_NEUTRAL


# ---------- build_color_request ----------

def test_build_color_request_targets_row_a_through_u():
    req = stage.build_color_request(123, 42, stage.COLOR_SUCCESS)
    rng = req["repeatCell"]["range"]
    assert rng["sheetId"] == 123
    assert rng["startRowIndex"] == 41  # 0-based
    assert rng["endRowIndex"] == 42
    assert rng["startColumnIndex"] == 0
    assert rng["endColumnIndex"] == 21  # A..U inclusive
    assert req["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"] == stage.COLOR_SUCCESS


# ---------- outcome_to_cells ----------

def _outcome(final_status: str = "ENRICHED", company_id: str = "10",
             deal_id: str = "100", rejected_reason: str = "") -> FullEnrichmentOutcome:
    return FullEnrichmentOutcome(
        input_kind="company_id",
        input_value="10",
        company_id=company_id,
        deal_id=deal_id,
        contact_ids=[],
        duplicate_company_ids=[],
        flags=[],
        steps=[
            StepOutcome(step="ENRICH_DIRECTOR_INN", status="DONE",
                        details={"summary": {"outcomes": [{"director_inn": "123456789012"}]}}),
        ],
        final_status=final_status,
        rejected_reason=rejected_reason,
        timestamp="2026-05-17T23:00:00+03:00",
        bitrix_links={},
    )


def test_outcome_to_cells_none_returns_exception_row():
    cells = stage.outcome_to_cells(None, bx=None, error_summary="boom")
    assert len(cells) == 13
    assert cells[2] == "EXCEPTION"   # col K (index 2 inside I-U slice)
    assert cells[12] == "boom"        # col U


def test_outcome_to_cells_writes_director_inn_into_col_s():
    cells = stage.outcome_to_cells(_outcome(), bx=None)
    assert len(cells) == 13
    assert cells[0] == "100"          # I deal_id
    assert cells[2] == "ENRICHED"     # K status
    assert cells[4] == "10"           # M company_id
    assert cells[10] == "123456789012"  # S director_inn


def test_outcome_to_cells_uses_bx_for_company_extras_when_available():
    class FakeBx:
        def get_company(self, cid):
            return {"TITLE": "ООО Test", "UF_CRM_1737098549301": "50000000"}

        def list_company_requisites(self, cid):
            return [{"RQ_INN": "7720238793"}]

        def get_deal(self, did):
            return {"STAGE_ID": "C50:NEW", "ASSIGNED_BY_ID": "2772"}

    cells = stage.outcome_to_cells(_outcome(), bx=FakeBx())
    assert cells[5] == "ООО Test"        # N company_title
    assert cells[6] == "7720238793"      # O company_inn
    assert cells[7] == "50000000"        # P revenue
    assert cells[8] == "C50:NEW"         # Q deal_stage
    assert cells[9] == "2772"            # R deal_assignee


# ---------- run_in_place: integration with fakes ----------

class FakeSheetsService:
    """Minimal googleapiclient-style mock."""

    def __init__(self, grid):
        self._grid = grid
        self.values_updates: list[tuple[str, list]] = []
        self.batch_updates: list[dict] = []

    def spreadsheets(self):  # noqa: ANN201
        outer = self

        class _SP:
            def get(self_inner, *, spreadsheetId, ranges, includeGridData, fields=None):
                class _E:
                    def execute(_):
                        return outer._grid
                return _E()

            def values(self_inner):
                class _V:
                    def update(__, *, spreadsheetId, range, valueInputOption, body):
                        outer.values_updates.append((range, body["values"][0]))
                        class _E:
                            def execute(_):
                                return {}
                        return _E()
                return _V()

            def batchUpdate(self_inner, *, spreadsheetId, body):
                outer.batch_updates.append(body)
                class _E:
                    def execute(_):
                        return {}
                return _E()

        return _SP()


class FakeBx:
    def get_company(self, cid):
        return {"TITLE": "Test Co", "UF_CRM_1737098549301": "100000000"}

    def list_company_requisites(self, cid):
        return [{"RQ_INN": "7720238793"}]

    def get_deal(self, did):
        return {"STAGE_ID": "C50:NEW", "ASSIGNED_BY_ID": "2772"}


def _grid_two_rows():
    return _grid([
        [_cell("Сделка")] + [_cell()] * 10,
        [_cell("a.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/100/")] + [_cell()] * 10,
        [_cell("b.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/200/")] + [_cell()] * 10,
    ])


def test_run_in_place_processes_unprocessed_rows(monkeypatch):
    svc = FakeSheetsService(_grid_two_rows())
    captured: list[dict] = []

    def fake_run(bx, **kwargs):
        captured.append(kwargs)
        return _outcome(deal_id=str(kwargs.get("deal_id") or ""))

    monkeypatch.setattr(stage.enrich_company_full, "run", fake_run)

    summary = stage.run_in_place(FakeBx(), svc, sheet_id="SHEET", tab_title="TestTab")

    assert summary["to_process"] == 2
    assert summary["processed"] == 2
    assert summary["failed"] == 0
    assert summary["status_counts"] == {"ENRICHED": 2}
    # both row writes
    assert len(svc.values_updates) == 2
    assert svc.values_updates[0][0] == "'TestTab'!I2:U2"
    assert svc.values_updates[1][0] == "'TestTab'!I3:U3"
    # both color requests
    assert len(svc.batch_updates) == 2
    assert all(
        b["requests"][0]["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"]
        == stage.COLOR_SUCCESS
        for b in svc.batch_updates
    )


def test_run_in_place_skips_already_processed_rows(monkeypatch):
    # row 2 has status filled → must be skipped
    row2 = [_cell("a.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/100/")] + [_cell()] * 10
    row2[10] = _cell("ENRICHED")
    row3 = [_cell("b.ru", "https://belberrycrm.bitrix24.ru/crm/deal/details/200/")] + [_cell()] * 10
    grid = _grid([
        [_cell("Сделка")] + [_cell()] * 10,
        row2,
        row3,
    ])
    svc = FakeSheetsService(grid)
    calls = []

    def fake_run(bx, **kwargs):
        calls.append(kwargs.get("deal_id"))
        return _outcome(deal_id=str(kwargs.get("deal_id") or ""))

    monkeypatch.setattr(stage.enrich_company_full, "run", fake_run)

    summary = stage.run_in_place(FakeBx(), svc, sheet_id="S", tab_title="TestTab")
    assert summary["already_processed_skipped"] == 1
    assert summary["to_process"] == 1
    assert calls == ["200"]


def test_run_in_place_records_exception_and_paints_red(monkeypatch):
    svc = FakeSheetsService(_grid_two_rows())

    def fake_run(bx, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(stage.enrich_company_full, "run", fake_run)

    summary = stage.run_in_place(FakeBx(), svc, sheet_id="S", tab_title="TestTab")

    assert summary["failed"] == 2
    assert summary["status_counts"] == {"EXCEPTION": 2}
    for b in svc.batch_updates:
        assert b["requests"][0]["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"] == stage.COLOR_FAILURE
    # error placed in col U (last cell of I-U slice)
    for _range, values in svc.values_updates:
        assert "network down" in values[-1]


def test_run_in_place_limit_caps_processing(monkeypatch):
    svc = FakeSheetsService(_grid_two_rows())

    def fake_run(bx, **kwargs):
        return _outcome(deal_id=str(kwargs.get("deal_id") or ""))

    monkeypatch.setattr(stage.enrich_company_full, "run", fake_run)

    summary = stage.run_in_place(FakeBx(), svc, sheet_id="S", tab_title="TestTab", limit=1)
    assert summary["to_process"] == 1
    assert summary["processed"] == 1
    assert len(svc.values_updates) == 1


def test_run_in_place_cron_outside_window_stops_immediately(monkeypatch):
    svc = FakeSheetsService(_grid_two_rows())

    def fake_run(bx, **kwargs):
        return _outcome()

    # Force "now" outside window via patching datetime.now indirectly:
    # is_within_window reads zoned dt; we just patch is_within_window to False.
    monkeypatch.setattr(stage, "is_within_window", lambda dt: False)
    monkeypatch.setattr(stage.enrich_company_full, "run", fake_run)

    summary = stage.run_in_place(FakeBx(), svc, sheet_id="S", tab_title="TestTab", cron_mode=True)
    assert summary["stopped_by_window"] == 1
    assert summary["processed"] == 0
    assert svc.values_updates == []


def test_run_in_place_raises_on_missing_sheet_gid():
    grid = {"sheets": [{"data": [{"rowData": []}]}]}  # no properties.sheetId
    svc = FakeSheetsService(grid)
    try:
        stage.run_in_place(FakeBx(), svc, sheet_id="S", tab_title="TestTab")
    except RuntimeError as exc:
        assert "sheet gid not found" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
