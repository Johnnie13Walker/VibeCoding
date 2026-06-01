from datetime import date

from src.db import build_upsert_sql
from src.writer import write_day


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append(sql)

    def executemany(self, sql, params):
        self.conn.sql.append(sql)


class Conn:
    def __init__(self):
        self.sql = []

    def cursor(self):
        return Cursor(self)


def test_build_upsert_sql_contains_natural_keys():
    sql = build_upsert_sql(
        "deals_snapshot",
        ["report_date", "deal_id", "title"],
        ["report_date", "deal_id"],
        ["title"],
    )

    assert "ON CONFLICT" in sql
    assert '"report_date", "deal_id"' in sql
    assert "DO UPDATE SET" in sql


def test_write_day_uses_upsert_for_reports_and_child_tables():
    conn = Conn()
    rows = {
        "deals_snapshot": [
            {
                "report_date": "2026-05-29",
                "deal_id": 1,
                "category_id": 10,
                "stage": "C10:NEW",
                "opportunity": 1,
                "manager_id": 10,
                "stuck_days": None,
                "stage_entered": None,
                "title": "deal",
                "company_id": None,
            }
        ],
        "meetings": [],
        "manager_activity": [],
        "kp_briefs": [],
    }

    counts = write_day(conn, date(2026, 5, 29), rows, "<html></html>", {"generated_at": "now"})

    joined = "\n".join(conn.sql)
    assert counts["reports"] == 1
    assert "ON CONFLICT" in joined
    assert '"report_date", "deal_id"' in joined
    assert 'INSERT INTO "reports"' in joined
