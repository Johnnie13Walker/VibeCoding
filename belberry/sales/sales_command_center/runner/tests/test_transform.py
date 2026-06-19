import json
from datetime import date, datetime, timedelta
from pathlib import Path

from src.timeutil import MSK
from src.transform import (
    aggregate_calls,
    age_level,
    build_db_rows,
    build_post_meeting_comms,
    compute_stale_deals,
    last_comm_date,
    manager_name,
    resolve_target_date,
    risk_reason,
    working_days_between,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "2026-05-29"
NOW = datetime(2026, 5, 30, 9, 0, tzinfo=MSK)


def load_raw():
    raw = json.loads((FIXTURE_DIR / "raw.json").read_text())
    raw["calls"] = json.loads((FIXTURE_DIR / "vox.json").read_text())
    raw["users"] = json.loads((FIXTURE_DIR / "users.json").read_text())
    raw["photos"] = json.loads((FIXTURE_DIR / "photos.json").read_text())
    raw.setdefault("wazzup", {})
    return raw


def test_last_comm_date_takes_max_of_call_and_wazzup():
    wazzup = {"1": [{"CREATED": "2026-05-25T12:00:00+03:00"}]}
    last_calls = {"1": "2026-05-20T10:00:00+03:00"}
    # Wazzup свежее звонка → берём дату Wazzup.
    assert last_comm_date(1, wazzup, last_calls) == "2026-05-25"
    # Звонок свежее переписки → берём дату звонка.
    last_calls = {"1": "2026-05-28T09:00:00+03:00"}
    assert last_comm_date(1, wazzup, last_calls) == "2026-05-28"


def test_last_comm_date_handles_single_or_missing_source():
    assert last_comm_date(7, {}, {"7": "2026-06-01T08:00:00+03:00"}) == "2026-06-01"
    assert last_comm_date(7, {"7": [{"CREATED": "2026-06-02T08:00:00+03:00"}]}, {}) == "2026-06-02"
    # Ни звонков, ни переписки → None (контакта с клиентом не было).
    assert last_comm_date(7, {}, {}) is None


def test_resolve_target_date_override():
    assert resolve_target_date("2026-05-29") == date(2026, 5, 29)


def test_working_days_between_counts_weekdays():
    assert working_days_between(date(2026, 5, 29), date(2026, 6, 2)) == 2


def test_compute_stale_deals_groups_stage_buckets():
    deal = {
        "ID": "1",
        "TITLE": "sporttravma.org",
        "STAGE_ID": "C10:EXECUTING",
        "OPPORTUNITY": "304000",
        "ASSIGNED_BY_ID": "10",
        "MOVED_TIME": (NOW - timedelta(days=45)).isoformat(),
        "LAST_ACTIVITY_TIME": (NOW - timedelta(days=10)).isoformat(),
    }

    stale = compute_stale_deals([deal], NOW)

    assert stale["Подготовка КП"][0]["deal_id"] == 1
    assert stale["Подготовка КП"][0]["age"] > 4
    assert stale["Подготовка КП"][0]["stage_threshold"] == 4
    assert stale["Подготовка КП"][0]["risk_reason"] == "молчит 10 дн"
    assert stale["Подготовка КП"][0]["age_level"] == "critical"


def test_deal_inside_threshold_is_not_stale():
    deal = {
        "ID": "1",
        "TITLE": "fresh",
        "STAGE_ID": "C10:EXECUTING",
        "OPPORTUNITY": "1",
        "ASSIGNED_BY_ID": "10",
        "MOVED_TIME": (NOW - timedelta(days=1)).isoformat(),
    }

    assert compute_stale_deals([deal], NOW) == {}


def test_wazzup_contact_suppresses_false_no_contact_age():
    deal = {
        "ID": "42",
        "TITLE": "wazzup fresh",
        "STAGE_ID": "C10:EXECUTING",
        "OPPORTUNITY": "100",
        "ASSIGNED_BY_ID": "10",
        "MOVED_TIME": (NOW - timedelta(days=10)).isoformat(),
        "LAST_ACTIVITY_TIME": (NOW - timedelta(days=30)).isoformat(),
    }
    wazzup = {"42": [{"CREATED": (NOW - timedelta(days=1)).isoformat()}]}

    stale = compute_stale_deals([deal], NOW, wazzup)

    assert stale["Подготовка КП"][0]["last_contact_days"] == 1


def test_risk_reason_tags_budget_contact_and_stage():
    assert risk_reason(0, 10, 4, 1) == "нет бюджета"
    assert risk_reason(100000, 10, 4, 8) == "молчит 8 дн"
    assert risk_reason(100000, 10, 4, 1) == "застрял на стадии"
    assert risk_reason(100000, 40, 4, 35) == "нет контакта"
    assert age_level(31, 4) == "critical"
    assert age_level(8, 4) == "warning"
    assert age_level(5, 4) == "normal"


def test_aggregate_calls_and_manager_name_from_fixture():
    raw = load_raw()

    stats = aggregate_calls(raw["calls"])

    assert stats
    assert max(row["dials_total"] for row in stats.values()) > 0
    assert any(row["calls_120s_plus"] > 0 for row in stats.values())
    assert manager_name(raw["users"], "2832") == "Вострецов Аркадий"


def test_aggregate_calls_hourly_buckets_by_msk_hour():
    from src.transform import aggregate_calls_hourly

    calls = [
        {"PORTAL_USER_ID": "2832", "CALL_DURATION": "19", "CALL_START_DATE": "2026-05-29T09:06:56+03:00"},
        {"PORTAL_USER_ID": "2832", "CALL_DURATION": "75", "CALL_START_DATE": "2026-05-29T09:30:00+03:00"},
        {"PORTAL_USER_ID": "2772", "CALL_DURATION": "0", "CALL_START_DATE": "2026-05-29T18:10:00+03:00"},
        {"PORTAL_USER_ID": None, "CALL_DURATION": "30", "CALL_START_DATE": "2026-05-29T10:00:00+03:00"},
    ]
    r = aggregate_calls_hourly(calls)
    assert r[(2832, 9)] == {"dials": 2, "answered": 2, "calls60": 1}
    assert r[(2772, 18)] == {"dials": 1}  # не ответили (duration 0)
    assert (None, 10) not in r  # без PORTAL_USER_ID — пропуск


def test_meetings_store_held_with_created_at_and_revenue():
    # Храним только ПРОВЕДЁННЫЕ (meet_day), одна строка на встречу. created_at и
    # company_revenue заполняются (для «назначены» в архиве — запрос по created_at,
    # без дубль-строки). meet_created_day отдельной строкой НЕ добавляется.
    raw = {
        "deals_open": [], "deals_created": [],
        "meet_day": [
            {"id": 1, "parentId2": 100, "assignedById": 10, "createdBy": 2772,
             "stageId": "DT1048_24:SUCCESS", "createdTime": "2026-06-01T09:00:00+03:00",
             "ufCrm16_1751009238": "2026-06-10T12:00:00+03:00"},
        ],
        "meet_created_day": [
            {"id": 2, "parentId2": 200, "assignedById": 11, "createdBy": 2772,
             "stageId": "DT1048_24:CLIENT", "createdTime": "2026-06-10T15:00:00+03:00",
             "ufCrm16_1751009238": "2026-06-18T10:00:00+03:00"},
        ],
        "meeting_deal_revenue": {100: 25_000_000.0},
    }
    rows = build_db_rows(raw, date(2026, 6, 10), NOW)
    mt = {r["meeting_id"]: r for r in rows["meetings"]}
    assert set(mt) == {1}  # только проведённая; назначенная-непроведённая (2) не строкой
    assert mt[1]["created_at"] is not None  # для запроса «назначены» по created_at
    assert mt[1]["company_revenue"] == 25_000_000.0
    assert mt[1]["created_by"] == 2772


def test_build_db_rows_matches_phase_one_schema_keys():
    raw = load_raw()

    rows = build_db_rows(raw, date(2026, 5, 29), NOW)

    assert set(rows) == {"deals_snapshot", "meetings", "manager_activity", "kp_briefs", "call_hourly"}
    assert len(rows["deals_snapshot"]) > 0
    assert set(rows["deals_snapshot"][0]) == {
        "report_date",
        "deal_id",
        "category_id",
        "stage",
        "opportunity",
        "manager_id",
        "stuck_days",
        "stage_entered",
        "last_comm_at",
        "title",
        "company_id",
    }
    assert set(rows["meetings"][0]) == {
        "report_date",
        "meeting_id",
        "deal_id",
        "meeting_type",
        "status",
        "manager_id",
        "created_by",
        "created_at",
        "scheduled_at",
        "company_revenue",
        "analysis_json",
        "transcript_url",
        "transcript_text",
        "transcript_ok",
        "analysis_status",
    }
    assert rows["meetings"][0]["analysis_json"] is None


def test_build_post_meeting_comms_only_after_meeting():
    meet_day = [{"id": 10, "parentId2": 100, "ufCrm16_1751009238": "2026-06-04T16:00:00+03:00"}]
    wazzup = {
        "100": [
            {"CREATED": "2026-06-04T15:00:00+03:00", "COMMENT": "до встречи — не итоги"},
            {"CREATED": "2026-06-04T17:30:00+03:00", "COMMENT": "Итоги встречи: договорились о КП"},
        ]
    }
    activities = [
        {"PROVIDER_ID": "CRM_EMAIL", "DIRECTION": "2", "OWNER_TYPE_ID": "2", "OWNER_ID": "100", "CREATED": "2026-06-04T18:00:00+03:00", "SUBJECT": "Итоги встречи и КП"},
        {"PROVIDER_ID": "CRM_EMAIL", "DIRECTION": "1", "OWNER_TYPE_ID": "2", "OWNER_ID": "100", "CREATED": "2026-06-04T19:00:00+03:00", "SUBJECT": "входящее — игнор"},
    ]
    out = build_post_meeting_comms(meet_day, wazzup, activities)
    text = out["10"]
    assert "Итоги встречи: договорились" in text  # Wazzup после встречи
    assert "Итоги встречи и КП" in text           # исходящее письмо после встречи
    assert "до встречи" not in text               # сообщение до встречи отброшено
    assert "входящее" not in text                 # входящее письмо отброшено


def test_build_db_rows_counts_cat10_entries_vhod_holod():
    # «Сделки» = вошедшие в C10:NEW за день; вход = создана в этот день, холод = раньше.
    raw = {
        "entered_deals": [
            # созданы 04.06 (день входа) → вход (2 шт)
            {"ID": "1", "ASSIGNED_BY_ID": "100", "DATE_CREATE": "2026-06-04T10:00:00+03:00"},
            {"ID": "2", "ASSIGNED_BY_ID": "100", "DATE_CREATE": "2026-06-04T11:00:00+03:00"},
            # создана раньше (12.02) → переведена из ТМ = холод
            {"ID": "9", "ASSIGNED_BY_ID": "100", "DATE_CREATE": "2026-02-12T09:00:00+03:00"},
        ],
        "won_deals": [
            {"ID": "1", "ASSIGNED_BY_ID": "100", "OPPORTUNITY": "150000"},
            {"ID": "9", "ASSIGNED_BY_ID": "100", "OPPORTUNITY": "50000.50"},
        ],
        "deals_open": [],
    }
    rows = build_db_rows(raw, date(2026, 6, 4), NOW)
    by_mgr = {r["manager_id"]: r for r in rows["manager_activity"]}
    assert 100 in by_mgr
    m = by_mgr[100]
    assert m["deals_incoming_count"] == 2  # вход: создана в день входа
    assert m["deals_cold_count"] == 1      # холод: создана раньше (переведена)
    assert m["deals_created_count"] == 3   # всего в Продажи = вход + холод
    assert m["deals_won_count"] == 2
    assert m["deals_won_amount"] == 200000.5


def test_briefs_kp_attributed_to_deal_owner():
    # Бриф/КП на сделке 100 (владелец 777), элемент назначен на 999 → кредит владельцу.
    # Услуга: бриф (1056, поле ufCrm20_1753290430 = 2730 → SEO), КП (1106, поле
    # ufCrm44_1774430907621 = 8662 → ORM) — разные enum-наборы, не путать.
    raw = {
        "deals_open": [{"ID": 100, "ASSIGNED_BY_ID": 777, "STAGE_ID": "C10:EXECUTING", "MOVED_TIME": "2026-06-01T10:00:00+03:00", "OPPORTUNITY": 0, "CATEGORY_ID": 10}],
        "deals_created": [],
        "briefs": [{"id": 1, "parentId2": 100, "assignedById": 999, "title": "b", "stageId": "X", "ufCrm20_1753290430": 2730}],
        "kp": [{"id": 2, "parentId2": 100, "assignedById": 999, "title": "k", "stageId": "X", "ufCrm44_1774430907621": 8662}],
    }
    rows = build_db_rows(raw, date(2026, 6, 4), NOW)
    ma = {r["manager_id"]: r for r in rows["manager_activity"]}
    assert ma[777]["briefs_created"] == 1
    assert ma[777]["kp_sent"] == 1
    assert 999 not in ma  # исполнитель элемента кредит НЕ получает
    kb = {r["item_id"]: r for r in rows["kp_briefs"]}
    assert kb[1]["manager_id"] == 777 and kb[2]["manager_id"] == 777
    assert kb[1]["service"] == "SEO"   # бриф
    assert kb[2]["service"] == "ORM"   # КП
    # Услуга не выбрана → пустая строка, не падаем.
    raw["briefs"][0].pop("ufCrm20_1753290430")
    rows2 = build_db_rows(raw, date(2026, 6, 4), NOW)
    assert {r["item_id"]: r for r in rows2["kp_briefs"]}[1]["service"] == ""


def test_briefs_fallback_to_assignee_when_deal_unknown():
    # Сделки нет в выборке (закрыта) → фолбэк на исполнителя элемента.
    raw = {
        "deals_open": [], "deals_created": [],
        "briefs": [{"id": 5, "parentId2": 555, "assignedById": 888, "title": "b", "stageId": "X"}],
        "kp": [],
    }
    rows = build_db_rows(raw, date(2026, 6, 4), NOW)
    ma = {r["manager_id"]: r for r in rows["manager_activity"]}
    assert ma[888]["briefs_created"] == 1
