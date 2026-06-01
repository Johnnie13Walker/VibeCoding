from datetime import date, datetime

import daily_runner
from src.timeutil import MSK


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append(sql)

    def fetchone(self):
        return None


class Conn:
    def __init__(self):
        self.sql = []
        self.committed = False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.committed = True


def test_runner_orchestrates_pipeline_on_empty_db(monkeypatch):
    order = []
    conn = Conn()

    monkeypatch.setattr(daily_runner, "load_config", lambda required: order.append("config"))
    monkeypatch.setattr(daily_runner.bx_client, "ensure_token_fresh", lambda: order.append("token"))
    monkeypatch.setattr(
        daily_runner,
        "collect_day",
        lambda target, bx=None: order.append("collect") or {"report_date": target.isoformat(), "deals_open": []},
    )
    monkeypatch.setattr(
        daily_runner,
        "build_db_rows",
        lambda raw, target, now: order.append("transform") or {
            "deals_snapshot": [],
            "meetings": [],
            "manager_activity": [],
            "kp_briefs": [],
        },
    )
    monkeypatch.setattr(daily_runner, "build_extras", lambda raw, now: {"raw": raw})
    monkeypatch.setattr(
        daily_runner,
        "render_report",
        lambda rows, extras: order.append("render") or "<!DOCTYPE html>",
    )
    monkeypatch.setattr(
        daily_runner,
        "write_day",
        lambda conn, target, rows, html, summary: order.append("write") or {"reports": 1},
    )

    result = daily_runner.run(
        date(2026, 5, 29),
        bx=object(),
        connect_fn=lambda: conn,
        now_fn=lambda: datetime(2026, 5, 30, 9, 0, tzinfo=MSK),
    )

    assert result["status"] == "done"
    assert order == ["config", "token", "collect", "transform", "render", "write"]
    assert conn.committed is True


def test_build_extras_extracts_rejections():
    raw = {
        "deals_open": [],
        "stagehistory": [{"OWNER_ID": 1, "STAGE_ID": "C10:LOSE"}],
        "deals_created": [{"ID": "1", "TITLE": "lost", "ASSIGNED_BY_ID": "10"}],
        "users": {"10": "Менеджер Тест"},
        "photos": {},
    }

    extras = daily_runner.build_extras(raw, datetime(2026, 5, 30, 9, 0, tzinfo=MSK))

    assert extras["rejections"][0]["title"] == "lost"
