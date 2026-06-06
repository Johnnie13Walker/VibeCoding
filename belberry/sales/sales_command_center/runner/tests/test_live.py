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
        # дата встречи = сегодня (проведено/отменено сегодня)
        "meetings": [
            {"id": 1, "assignedById": 10, "createdBy": 10, "title": "kandela.ru", "ufCrm16_1751009238": "2026-06-04T10:00:00", "parentId2": 555, "stageId": "DT1048_24:SUCCESS"},
            {"id": 2, "assignedById": 12, "createdBy": 12, "title": "renewal.ru", "ufCrm16_1751009238": "2026-06-04T18:00:00", "parentId2": 556, "stageId": "DT1048_24:FAIL"},
        ],
        # созданы сегодня (назначено сегодня) — встреча на будущую дату
        "meetings_set": [
            {"id": 3, "assignedById": 10, "createdBy": 10, "title": "future.ru", "ufCrm16_1751009238": "2026-06-08T11:00:00", "parentId2": 557, "stageId": "DT1048_24:NEW"},
        ],
        "briefs": [
            {"id": 1530, "assignedById": 10, "title": "rant.ru", "parentId2": 777, "ufCrm20_1753290430": 2726},
            {"id": 1526, "assignedById": 12, "title": "cryplat.ru", "parentId2": 778, "ufCrm20_1753290430": "2730"},
        ],
        "deals_created": [{"ASSIGNED_BY_ID": 10, "TITLE": "newdeal.ru", "DATE_CREATE": "2026-06-04T11:00:00"}],
        "kp": [{"assignedById": 12, "title": "КП", "updatedTime": "2026-06-04T12:00:00"}],
        "activities": [
            {"PROVIDER_ID": "CRM_EMAIL", "DIRECTION": "2", "AUTHOR_ID": 10},
            {"PROVIDER_ID": "CRM_EMAIL", "DIRECTION": "1", "AUTHOR_ID": 12},  # входящее — не считаем
            {"PROVIDER_ID": "VOXIMPLANT_CALL", "DIRECTION": "2", "AUTHOR_ID": 10},  # звонок — не письмо
        ],
    }

    p = build_live_payload(date(2026, 6, 4), raw, now)

    assert p["totals"] == {
        "dials": 3, "answered": 2, "calls60": 2,
        "meetings": 3, "meetings_held": 1, "meetings_scheduled": 1, "meetings_cancelled": 1,
        "briefs": 2, "kp": 1, "deals": 1, "deals_spam": 0, "emails": 1,
    }
    by_id = {m["manager_id"]: m for m in p["managers"]}
    # У 10: встреча проведена сегодня (id1) + назначена сегодня на будущее (id3)
    assert by_id[10]["m_held"] == 1 and by_id[10]["m_scheduled"] == 1 and by_id[10]["meetings"] == 2
    assert by_id[10]["calls60"] == 1 and by_id[10]["briefs"] == 1 and by_id[10]["deals"] == 1
    assert by_id[10]["emails"] == 1 and by_id[12]["emails"] == 0
    assert by_id[12]["m_cancelled"] == 1 and by_id[12]["calls60"] == 1 and by_id[12]["briefs"] == 1 and by_id[12]["kp"] == 1
    # Лента: встречи дня(2)+брифы(2)+КП(1)+сделки(1) = 6 (назначенная на будущее в ленту не идёт)
    assert len(p["feed"]) == 6

    # списки: SUCCESS→held, FAIL→cancelled, назначенная сегодня→scheduled + флаг set_today
    assert len(p["meetings_list"]) == 3
    by_mid = {m["id"]: m for m in p["meetings_list"]}
    assert by_mid[1]["status"] == "held" and by_mid[2]["status"] == "cancelled" and by_mid[3]["status"] == "scheduled"
    assert by_mid[3]["set_today"] is True and by_mid[1]["set_today"] is False
    briefs = {b["id"]: b for b in p["briefs_list"]}
    assert briefs[1530]["service"] == "Контекстная реклама" and briefs[1530]["deal_id"] == 777
    assert briefs[1526]["service"] == "SEO"  # строковый enum-id тоже мапится


def test_live_scheduled_today_credited_to_creator_not_responsible():
    """Встречу, назначенную сегодня на будущее, засчитываем СОЗДАТЕЛЮ (телемаркетолог),
    а не ответственному продавцу (он её только проведёт)."""
    now = datetime(2026, 6, 4, 15, 0, tzinfo=MSK)
    raw = {
        "calls": [],
        "meetings": [],
        # ТМ-сотрудник 12 создал встречу, ответственным поставил продавца 10
        "meetings_set": [
            {"id": 9, "assignedById": 10, "createdBy": 12, "title": "lcenter.ru",
             "ufCrm16_1751009238": "2026-06-08T11:00:00", "parentId2": 11490, "stageId": "DT1048_24:NEW"},
        ],
        "briefs": [], "deals_created": [], "kp": [], "activities": [],
    }
    p = build_live_payload(date(2026, 6, 4), raw, now)
    by_id = {m["manager_id"]: m for m in p["managers"]}
    # назначено засчитано создателю 12, продавец 10 не появляется
    assert by_id[12]["m_scheduled"] == 1 and by_id[12]["meetings"] == 1
    assert 10 not in by_id
    # в ленте встреч владелец — создатель
    assert p["meetings_list"][0]["manager_id"] == 12 and p["meetings_list"][0]["set_today"] is True


def test_live_excludes_spam_deals():
    """СПАМ-сделки (UF_CRM_1771495464=8588) не идут в «сделок создано»."""
    now = datetime(2026, 6, 4, 15, 0, tzinfo=MSK)
    raw = {
        "calls": [{"PORTAL_USER_ID": 10, "CALL_DURATION": 130}],
        "meetings": [], "meetings_set": [], "briefs": [], "kp": [], "activities": [],
        "deals_created": [
            {"ASSIGNED_BY_ID": 10, "TITLE": "real.ru", "DATE_CREATE": "2026-06-04T11:00:00"},
            {"ASSIGNED_BY_ID": 10, "TITLE": "spam.ru", "DATE_CREATE": "2026-06-04T12:00:00", "UF_CRM_1771495464": "8588"},
        ],
    }
    p = build_live_payload(date(2026, 6, 4), raw, now)
    assert p["totals"]["deals"] == 1 and p["totals"]["deals_spam"] == 1
    by_id = {m["manager_id"]: m for m in p["managers"]}
    assert by_id[10]["deals"] == 1
    # спам-сделка не попала и в ленту
    assert all(e["title"] != "spam.ru" for e in p["feed"])


def test_build_live_payload_empty():
    now = datetime(2026, 6, 4, 9, 0, tzinfo=MSK)
    p = build_live_payload(date(2026, 6, 4), {"calls": [], "meetings": [], "deals_created": [], "kp": [], "briefs": []}, now)
    assert p["totals"]["dials"] == 0 and p["managers"] == [] and p["meetings_list"] == [] and p["briefs_list"] == []
