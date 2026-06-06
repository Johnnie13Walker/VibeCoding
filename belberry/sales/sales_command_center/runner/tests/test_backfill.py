from datetime import date, datetime

from src import backfill
from src.timeutil import MSK


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append((sql, params))
        self._last = sql

    def executemany(self, sql, params):
        self.conn.sql.append((sql, list(params)))

    def fetchall(self):
        # Заготовленные строки только для SELECT preserve (messenger_dialogs).
        if "messenger_dialogs" in getattr(self, "_last", ""):
            return list(self.conn.preserved_rows)
        return []


class Conn:
    def __init__(self, preserved_rows=()):
        self.sql = []
        self.commits = 0
        self.preserved_rows = preserved_rows

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1


def test_write_flow_day_preserves_chats_across_rebuild():
    # У менеджера 1 уже есть чаты (посчитал боевой раннер). backfill пересобирает
    # manager_activity, но обязан вернуть messenger_dialogs обратно.
    conn = Conn(preserved_rows=[(1, 4)])
    rows = {
        "manager_activity": [{"report_date": "2026-02-02", "manager_id": 1, "calls_total": 5, "messenger_dialogs": 0}],
        "meetings": [],
        "kp_briefs": [],
    }
    backfill.write_flow_day(conn, date(2026, 2, 2), rows, datetime(2026, 2, 3, 9, tzinfo=MSK))
    restores = [(s, p) for s, p in conn.sql if s.startswith("UPDATE manager_activity SET messenger_dialogs")]
    assert restores == [("UPDATE manager_activity SET messenger_dialogs = %s WHERE report_date = %s AND manager_id = %s", (4, "2026-02-02", 1))]


def test_write_flow_day_stub_delete_and_upserts():
    conn = Conn()
    rows = {
        "manager_activity": [{"report_date": "2026-02-02", "manager_id": 1, "calls_total": 5}],
        "meetings": [],
        "kp_briefs": [],
    }
    counts = backfill.write_flow_day(conn, date(2026, 2, 2), rows, datetime(2026, 2, 3, 9, tzinfo=MSK))
    joined = " ".join(s for s, _ in conn.sql)
    assert "INSERT INTO reports" in joined
    assert "DO NOTHING" in joined  # реальные отчёты не затираем
    # пересобираемые таблицы чистятся за день (убрать остаточные строки)
    assert 'DELETE FROM "manager_activity" WHERE report_date' in joined
    assert 'DELETE FROM "kp_briefs" WHERE report_date' in joined
    assert counts["manager_activity"] == 1
    assert counts["meetings"] == 0


def test_write_flow_day_preserves_meeting_analysis():
    conn = Conn()
    rows = {
        "manager_activity": [],
        "meetings": [
            {"report_date": "2026-02-02", "meeting_id": 7, "meeting_type": "briefing", "analysis_json": None, "transcript_text": None}
        ],
        "kp_briefs": [],
    }
    backfill.write_flow_day(conn, date(2026, 2, 2), rows, datetime(2026, 2, 3, 9, tzinfo=MSK))
    # upsert meetings: в DO UPDATE SET не должно быть analysis_json/transcript_text
    meet_sql = [s for s, _ in conn.sql if '"meetings"' in s][0]
    assert "DO UPDATE SET" in meet_sql
    upd = meet_sql.split("DO UPDATE SET", 1)[1]
    assert "analysis_json" not in upd
    assert "transcript_text" not in upd
    assert "meeting_type" in upd  # обычные колонки обновляются


def test_backfill_range_skips_weekends(monkeypatch):
    monkeypatch.setattr(backfill, "collect_flow_day", lambda d, bx=None: {"won_deals": [], "deals_created": []})
    monkeypatch.setattr(
        backfill,
        "build_db_rows",
        lambda raw, d, now: {
            "manager_activity": [{"report_date": d.isoformat(), "manager_id": 1}],
            "meetings": [],
            "kp_briefs": [],
        },
    )
    # 06.02 пт, 07-08 выходные, 09.02 пн → считаются только пт и пн.
    totals = backfill.backfill_range(date(2026, 2, 6), date(2026, 2, 9), conn=None, dry_run=True)
    assert totals["days"] == 2
    assert totals["manager_activity"] == 2


def test_collect_flow_day_skips_snapshot_and_analysis():
    # FakeBx из test_collect повторяет контракт; здесь проверяем форму выдачи.
    from tests.test_collect import FakeBx

    raw = backfill.collect_flow_day(date(2026, 5, 15), bx=FakeBx())
    assert raw["deals_open"] == []  # снимок не собираем
    assert "report_date" in raw and raw["report_date"] == "2026-05-15"
    assert "won_deals" in raw and "deals_created" in raw
