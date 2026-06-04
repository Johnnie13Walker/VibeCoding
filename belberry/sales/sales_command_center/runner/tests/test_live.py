from datetime import date, datetime

from src.live import build_live_payload
from src.timeutil import MSK


def test_build_live_payload_aggregates_with_briefs_and_meetings():
    now = datetime(2026, 6, 4, 15, 0, tzinfo=MSK)
    raw = {
        "calls": [
            {"PORTAL_USER_ID": 10, "CALL_DURATION": 130},
            {"PORTAL_USER_ID": 10, "CALL_DURATION": 0},
            {"PORTAL_USER_ID": 12, "CALL_DURATION": 60},
        ],
        "meetings": [
            {"id": 1, "assignedById": 10, "title": "kandela.ru", "ufCrm16_1751009238": "2026-06-04T10:00:00", "parentId2": 555},
            {"id": 2, "assignedById": 12, "title": "renewal.ru", "ufCrm16_1751009238": "2026-06-04T18:00:00", "parentId2": 556},
        ],
        "briefs": [
            {"id": 1530, "assignedById": 10, "title": "rant.ru", "parentId2": 777, "ufCrm20_1753290430": 2726},
            {"id": 1526, "assignedById": 12, "title": "cryplat.ru", "parentId2": 778, "ufCrm20_1753290430": "2730"},
        ],
        "deals_created": [{"ASSIGNED_BY_ID": 10, "TITLE": "newdeal.ru", "DATE_CREATE": "2026-06-04T11:00:00"}],
        "kp": [{"assignedById": 12, "title": "КП", "updatedTime": "2026-06-04T12:00:00"}],
    }

    p = build_live_payload(date(2026, 6, 4), raw, now)

    assert p["totals"] == {
        "dials": 3, "answered": 2, "calls60": 2,
        "meetings": 2, "meetings_done": 1, "briefs": 2, "kp": 1, "deals": 1,
    }
    by_id = {m["manager_id"]: m for m in p["managers"]}
    assert by_id[10]["calls60"] == 1 and by_id[10]["briefs"] == 1 and by_id[10]["meetings"] == 1 and by_id[10]["deals"] == 1
    assert by_id[12]["calls60"] == 1 and by_id[12]["briefs"] == 1 and by_id[12]["kp"] == 1
    # Лента: встречи(2)+брифы(2)+КП(1)+сделки(1) = 6
    assert len(p["feed"]) == 6

    # списки
    assert len(p["meetings_list"]) == 2
    done = {m["id"]: m["done"] for m in p["meetings_list"]}
    assert done[1] is True and done[2] is False  # 10:00 прошло, 18:00 впереди
    briefs = {b["id"]: b for b in p["briefs_list"]}
    assert briefs[1530]["service"] == "Контекстная реклама" and briefs[1530]["deal_id"] == 777
    assert briefs[1526]["service"] == "SEO"  # строковый enum-id тоже мапится


def test_build_live_payload_empty():
    now = datetime(2026, 6, 4, 9, 0, tzinfo=MSK)
    p = build_live_payload(date(2026, 6, 4), {"calls": [], "meetings": [], "deals_created": [], "kp": [], "briefs": []}, now)
    assert p["totals"]["dials"] == 0 and p["managers"] == [] and p["meetings_list"] == [] and p["briefs_list"] == []
