from datetime import date, datetime
from contextlib import contextmanager

import daily_runner
from src.lock import AlreadyRunning
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

    def fetchall(self):
        return self.conn.rows

    def executemany(self, sql, params):
        self.conn.sql.append(sql)


class Conn:
    def __init__(self):
        self.sql = []
        self.rows = []
        self.committed = False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


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
    monkeypatch.setattr(daily_runner.analyze_llm, "get_client", lambda: object())
    monkeypatch.setattr(daily_runner, "run_llm_phase", lambda *a, **k: {"analyses": {}, "narrative": {}})
    monkeypatch.setattr(
        daily_runner,
        "write_day",
        lambda conn, target, rows, html, summary, status="done": order.append("write") or {"reports": 1},
    )

    result = daily_runner.run(
        date(2026, 5, 29),
        bx=object(),
        connect_fn=lambda: conn,
        now_fn=lambda: datetime(2026, 5, 30, 9, 0, tzinfo=MSK),
    )

    assert result["status"] == "done"
    # Дневной отчёт отключён: HTML не авторится/не рендерится — сразу запись данных.
    assert result["html"] == ""
    assert order == ["config", "token", "collect", "transform", "write"]
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


def test_llm_failure_keeps_deterministic_report(monkeypatch):
    conn = Conn()
    captured = {}
    monkeypatch.setattr(daily_runner, "load_config", lambda required: None)
    monkeypatch.setattr(daily_runner.bx_client, "ensure_token_fresh", lambda: None)
    monkeypatch.setattr(daily_runner, "collect_day", lambda target, bx=None: {"report_date": target.isoformat(), "deals_open": [], "meet_day": []})
    monkeypatch.setattr(daily_runner, "build_db_rows", lambda raw, target, now: {"deals_snapshot": [], "meetings": [], "manager_activity": [], "kp_briefs": []})
    monkeypatch.setattr(daily_runner, "run_llm_phase", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    def fake_write(conn, target, rows, html, summary, status="done"):
        captured["status"] = status
        captured["html"] = html
        return {"reports": 1}

    monkeypatch.setattr(daily_runner, "write_day", fake_write)

    daily_runner.run(date(2026, 5, 29), connect_fn=lambda: conn)

    # Сбой LLM-разбора встреч → partial; данные дня всё равно пишутся (html пустой).
    assert captured["status"] == "partial_llm_failure"
    assert captured["html"] == ""
    assert conn.committed is True


def test_llm_success_marks_done_and_transcripts_written(monkeypatch):
    conn = Conn()
    captured = {}
    rows = {"deals_snapshot": [], "meetings": [{"meeting_id": 2180}], "manager_activity": [], "kp_briefs": []}
    monkeypatch.setattr(daily_runner, "load_config", lambda required: None)
    monkeypatch.setattr(daily_runner.bx_client, "ensure_token_fresh", lambda: None)
    monkeypatch.setattr(daily_runner, "collect_day", lambda target, bx=None: {"report_date": target.isoformat(), "deals_open": [], "meet_day": [{"id": 2180}]})
    monkeypatch.setattr(daily_runner, "build_db_rows", lambda raw, target, now: rows)

    def fake_llm(raw, rows, extras, client_factory=None, bx=None):
        rows["meetings"][0]["transcript_text"] = "текст"
        return {"analyses": {2180: {"transcript_status": "ok"}}, "narrative": {}}

    monkeypatch.setattr(daily_runner, "run_llm_phase", fake_llm)
    monkeypatch.setattr(daily_runner.analyze_llm, "get_client", lambda: object())

    def fake_write(conn, target, rows, html, summary, status="done"):
        captured["status"] = status
        captured["rows"] = rows
        captured["html"] = html
        return {"reports": 1}

    monkeypatch.setattr(daily_runner, "write_day", fake_write)

    daily_runner.run(date(2026, 5, 29), connect_fn=lambda: conn)

    assert captured["status"] == "done"
    # Разбор встреч сохранён (нужен /meetings), HTML-отчёта больше нет.
    assert captured["rows"]["meetings"][0]["transcript_text"] == "текст"
    assert captured["html"] == ""


@contextmanager
def unlocked():
    yield


def test_cron_entry_done_success_no_telegram():
    alerts = []

    code = daily_runner.cron_entry(
        date(2026, 5, 29),
        run_fn=lambda target, force=False: {
            "status": "done",
            "report_date": "2026-05-29",
            "llm_status": "done",
        },
        lock_ctx=unlocked,
        notify_alert=lambda message, report_date=None: alerts.append((message, report_date)) or True,
    )

    # Дневной отчёт отключён — в Telegram ничего не шлём, алертов нет.
    assert code == 0
    assert alerts == []


def test_cron_entry_alerts_on_partial():
    alerts = []

    code = daily_runner.cron_entry(
        date(2026, 5, 29),
        run_fn=lambda target, force=False: {
            "status": "done",
            "report_date": "2026-05-29",
            "llm_status": "partial_llm_failure",
        },
        lock_ctx=unlocked,
        notify_alert=lambda message, report_date=None: alerts.append((message, report_date)) or True,
    )

    assert code == 0
    assert alerts == [("LLM-разбор встреч недоступен (данные собраны)", "2026-05-29")]


def test_cron_entry_alerts_on_exception():
    alerts = []

    def fail(target, force=False):
        raise RuntimeError("boom ANTHROPIC_API_KEY")

    code = daily_runner.cron_entry(
        date(2026, 5, 29),
        run_fn=fail,
        lock_ctx=unlocked,
        notify_alert=lambda message, report_date=None: alerts.append((message, report_date)) or True,
    )

    assert code == 1
    assert alerts == [("boom ***", "2026-05-29")]


def test_cron_entry_blocked_when_running():
    calls = []

    @contextmanager
    def locked():
        raise AlreadyRunning("busy")
        yield

    code = daily_runner.cron_entry(
        date(2026, 5, 29),
        run_fn=lambda target, force=False: calls.append("run"),
        lock_ctx=locked,
        notify_alert=lambda message, report_date=None: calls.append("alert"),
    )

    assert code == 0
    assert calls == []


def test_cron_entry_skipped_sends_nothing():
    calls = []

    code = daily_runner.cron_entry(
        date(2026, 5, 29),
        run_fn=lambda target, force=False: {
            "status": "skipped",
            "report_date": "2026-05-29",
        },
        lock_ctx=unlocked,
        notify_alert=lambda message, report_date=None: calls.append("alert"),
    )

    assert code == 0
    assert calls == []
