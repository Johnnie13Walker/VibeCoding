import json
from datetime import date
from pathlib import Path

from src import bx_client
from src.collect import collect_day
from src.timeutil import next_working_day

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "2026-05-29"


class FakeBx:
    def __init__(self):
        self.fetches = []
        self.calls = []

    def fetch_all(self, method, params=None, idfield="ID", cap=5000):
        self.fetches.append((method, params or {}, idfield))
        if method == "crm.deal.list" and "DATE_CREATE" in str(params):
            return [{"ID": "10", "TITLE": "new deal", "ASSIGNED_BY_ID": "1"}]
        if method == "crm.deal.list":
            return [
                {
                    "ID": "20",
                    "TITLE": "open deal",
                    "CATEGORY_ID": "10",
                    "STAGE_ID": "C10:EXECUTING",
                    "ASSIGNED_BY_ID": "1",
                    "MOVED_TIME": "2026-05-01T10:00:00+03:00",
                    "LAST_ACTIVITY_TIME": "2026-05-28T10:00:00+03:00",
                }
            ]
        if method == "crm.stagehistory.list":
            return [{"ID": 1, "OWNER_ID": 20, "STAGE_ID": "C10:LOSE"}]
        if method == "crm.item.list":
            entity_type = params["entityTypeId"]
            if entity_type == 1048 and "ufCrm16_1751009238" in str(params):
                lower = params["filter"].get(">=ufCrm16_1751009238", "")
                if lower.startswith(next_working_day(date(2026, 5, 29)).isoformat()):
                    return [
                        {
                            "id": 104,
                            "title": "future meeting",
                            "assignedById": 1,
                            "parentId2": 20,
                            "ufCrm16_1751009238": "2026-06-01T10:00:00+03:00",
                        }
                    ]
                if lower.startswith("2026-05-29"):
                    return [
                        {
                            "id": 103,
                            "title": "day meeting",
                            "assignedById": 1,
                            "parentId2": 20,
                            "ufCrm16_1751009238": "2026-05-29T10:00:00+03:00",
                        }
                    ]
            if entity_type == 1048:
                return []
            if entity_type == 1056:
                return [{"id": 1056, "title": "brief", "assignedById": 1, "parentId2": 20}]
            if entity_type == 1106:
                return [{"id": 1106, "title": "kp", "assignedById": 1, "parentId2": 20}]
        if method == "crm.activity.list":
            return [{"ID": "500", "OWNER_ID": "20", "RESPONSIBLE_ID": "1"}]
        return []

    def call(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "voximplant.statistic.get":
            last = int((params or {}).get("FILTER", {}).get(">ID", 0))
            if last == 0:
                return {"result": [{"ID": "1", "PORTAL_USER_ID": "1", "CALL_DURATION": "130"}]}
            return {"result": []}
        if method == "user.get":
            return {"result": [{"ID": "1", "LAST_NAME": "Иванов", "NAME": "Иван"}]}
        if method == "crm.timeline.comment.list":
            return {"result": []}
        return {"result": []}


def test_seed_fixture_has_data_contract_keys():
    raw = json.loads((FIXTURE_DIR / "raw.json").read_text())

    for key in ["deals_open", "meet_day", "stagehistory", "briefs", "kp", "activities"]:
        assert key in raw
        assert isinstance(raw[key], list)


def test_collect_day_uses_fake_client_without_network():
    raw = collect_day(date(2026, 5, 29), bx=FakeBx())

    assert raw["deals_created"]
    assert raw["calls"]
    assert "photos" in raw
    assert raw["users"] == {"1": "Иванов Иван"}


def test_meet_today_uses_next_working_day_not_wall_clock():
    fake = FakeBx()

    raw = collect_day(date(2026, 5, 29), bx=fake)

    assert raw["meet_today"][0]["ufCrm16_1751009238"].startswith("2026-06-01")


def test_fetch_all_cursor_stops_on_empty_page(monkeypatch):
    pages = [
        {"result": [{"ID": 1}, {"ID": 2}]},
        {"result": []},
    ]
    calls = []

    def fake_call(method, params=None):
        calls.append(params)
        return pages.pop(0)

    monkeypatch.setattr(bx_client, "call", fake_call)

    rows = bx_client.fetch_all("crm.deal.list")

    assert rows == [{"ID": 1}, {"ID": 2}]
    assert len(calls) == 2
    assert calls[0]["filter"][">ID"] == 0
    assert calls[1]["filter"][">ID"] == 2
    assert calls[0]["start"] == -1
