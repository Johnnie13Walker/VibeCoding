from datetime import date, datetime

from src.live import build_live_payload
from src.timeutil import MSK


def test_build_live_payload_aggregates_totals_and_managers():
    now = datetime(2026, 6, 4, 15, 0, tzinfo=MSK)
    raw = {
        "calls": [
            {"PORTAL_USER_ID": 10, "CALL_DURATION": 130},
            {"PORTAL_USER_ID": 10, "CALL_DURATION": 0},
            {"PORTAL_USER_ID": 12, "CALL_DURATION": 60},
        ],
        "meetings": [
            {"assignedById": 10, "title": "kandela.ru", "ufCrm16_1751009238": "2026-06-04T10:00:00"},
            {"assignedById": 12, "title": "renewal.ru", "ufCrm16_1751009238": "2026-06-04T18:00:00"},
        ],
        "deals_created": [{"ASSIGNED_BY_ID": 10, "TITLE": "newdeal.ru", "DATE_CREATE": "2026-06-04T11:00:00"}],
        "kp": [{"assignedById": 12, "title": "КП renewal", "updatedTime": "2026-06-04T12:00:00"}],
    }

    p = build_live_payload(date(2026, 6, 4), raw, now)

    assert p["report_date"] == "2026-06-04"
    assert p["totals"] == {
        "dials": 3, "answered": 2, "calls120": 1,
        "meetings": 2, "meetings_done": 1, "kp": 1, "deals": 1,
    }
    by_id = {m["manager_id"]: m for m in p["managers"]}
    assert by_id[10]["dials"] == 2 and by_id[10]["calls120"] == 1 and by_id[10]["meetings"] == 1 and by_id[10]["deals"] == 1
    assert by_id[12]["answered"] == 1 and by_id[12]["meetings"] == 1 and by_id[12]["kp"] == 1
    assert len(p["feed"]) == 4
    # лента отсортирована по времени убыв.
    ats = [e["at"] for e in p["feed"]]
    assert ats == sorted(ats, reverse=True)


def test_build_live_payload_empty():
    now = datetime(2026, 6, 4, 9, 0, tzinfo=MSK)
    p = build_live_payload(date(2026, 6, 4), {"calls": [], "meetings": [], "deals_created": [], "kp": []}, now)
    assert p["totals"]["dials"] == 0 and p["managers"] == [] and p["feed"] == []
