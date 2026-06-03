import json
from datetime import date, datetime, timedelta
from pathlib import Path

from src.timeutil import MSK
from src.transform import (
    aggregate_calls,
    age_level,
    build_db_rows,
    compute_stale_deals,
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


def test_build_db_rows_matches_phase_one_schema_keys():
    raw = load_raw()

    rows = build_db_rows(raw, date(2026, 5, 29), NOW)

    assert set(rows) == {"deals_snapshot", "meetings", "manager_activity", "kp_briefs"}
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
        "scheduled_at",
        "analysis_json",
        "transcript_url",
        "transcript_text",
        "transcript_ok",
        "analysis_status",
    }
    assert rows["meetings"][0]["analysis_json"] is None
