from __future__ import annotations

from sales_kpi_dashboard.sheet_schema import bootstrap_schema


class FakeSheetsClient:
    def __init__(self, tabs: dict[str, int], values: dict[str, list[list[object]]] | None = None):
        self.tabs = dict(tabs)
        self.values = values or {}
        self.calls: list[tuple[str, dict]] = []
        self.service = FakeService()

    def get_tabs(self) -> dict[str, int]:
        return dict(self.tabs)

    def _execute(self, request: tuple[str, dict]):
        kind, payload = request
        self.calls.append(request)
        if kind == "batchUpdate":
            for req in payload["body"]["requests"]:
                if "addSheet" in req:
                    title = req["addSheet"]["properties"]["title"]
                    self.tabs[title] = max(self.tabs.values(), default=0) + 1
                if "updateSheetProperties" in req:
                    props = req["updateSheetProperties"]["properties"]
                    old_title = next(title for title, sheet_id in self.tabs.items() if sheet_id == props["sheetId"])
                    self.tabs.pop(old_title)
                    self.tabs[props["title"]] = props["sheetId"]
            return {"replies": []}
        if kind == "values_get":
            tab = payload["range"].split("'")[1]
            return {"values": self.values.get(tab, [])[:1]}
        if kind == "values_update":
            tab = payload["range"].split("'")[1]
            self.values[tab] = payload["body"]["values"]
            return {}
        raise AssertionError(kind)


class FakeService:
    def spreadsheets(self):
        return FakeSpreadsheets()


class FakeSpreadsheets:
    def batchUpdate(self, spreadsheetId: str, body: dict):  # noqa: N802 - Google API style
        return ("batchUpdate", {"spreadsheetId": spreadsheetId, "body": body})

    def values(self):
        return FakeValues()


class FakeValues:
    def get(self, spreadsheetId: str, range: str, **_kwargs):  # noqa: A002 - Google API style
        return ("values_get", {"spreadsheetId": spreadsheetId, "range": range})

    def update(self, spreadsheetId: str, range: str, valueInputOption: str, body: dict):  # noqa: A002,N802
        return (
            "values_update",
            {
                "spreadsheetId": spreadsheetId,
                "range": range,
                "valueInputOption": valueInputOption,
                "body": body,
            },
        )


def test_bootstrap_schema_creates_tabs_seeds_plan_and_archives_list1() -> None:
    client = FakeSheetsClient({"Лист1": 0})

    report = bootstrap_schema(client)

    assert report["created"] == ["Plan", "tm_metrics", "sales_plan", "mop_metrics", "sync_log"]
    assert "Plan" in report["seeded"]
    assert "sync_log" in report["seeded"]
    assert report["archived"] == ["Лист1 → _archive_лист1 (hidden)"]
    add_sheet_calls = [
        req
        for kind, payload in client.calls
        if kind == "batchUpdate"
        for req in payload["body"]["requests"]
        if "addSheet" in req
    ]
    assert len(add_sheet_calls) == 5
    update_props = [
        req["updateSheetProperties"]
        for kind, payload in client.calls
        if kind == "batchUpdate"
        for req in payload["body"]["requests"]
        if "updateSheetProperties" in req
    ]
    assert update_props[0]["properties"]["title"] == "_archive_лист1"
    assert update_props[0]["properties"]["hidden"] is True
    assert client.values["Plan"][0] == ["Period", "Metric", "Dimension", "Value", "Comment"]


def test_bootstrap_schema_dry_run_does_not_write() -> None:
    client = FakeSheetsClient({"Лист1": 0})

    report = bootstrap_schema(client, dry_run=True)

    assert report["dry_run"] == ["true"]
    assert report["created"] == ["Plan", "tm_metrics", "sales_plan", "mop_metrics", "sync_log"]
    assert client.calls == []


def test_bootstrap_schema_is_idempotent_when_tabs_are_seeded() -> None:
    tabs = {"Plan": 1, "tm_metrics": 2, "sales_plan": 3, "mop_metrics": 4, "sync_log": 5, "_archive_лист1": 0}
    values = {"Plan": [["Period", "Metric"]], "sync_log": [["ts", "status"]]}
    client = FakeSheetsClient(tabs, values)

    report = bootstrap_schema(client)

    assert report["created"] == []
    assert report["seeded"] == []
    assert report["archived"] == []
    add_sheet_calls = [
        req
        for kind, payload in client.calls
        if kind == "batchUpdate"
        for req in payload["body"]["requests"]
        if "addSheet" in req
    ]
    assert add_sheet_calls == []
