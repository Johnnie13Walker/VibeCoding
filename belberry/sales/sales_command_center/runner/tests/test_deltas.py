from datetime import date

from src.deltas import compute_deltas, delta_label, metric_delta, metrics_from_rows


def test_metrics_from_rows_counts_key_values():
    rows = {
        "meetings": [{"meeting_id": 1}, {"meeting_id": 2}],
        "kp_briefs": [{"item_type": "kp"}, {"item_type": "brief"}],
        "manager_activity": [
            {"dials_total": 10, "calls_answered": 4, "deals_created_count": 1, "kp_sent": 3},
            {"dials_total": 30, "calls_answered": 6, "deals_created_count": 2, "kp_sent": 0},
        ],
    }

    metrics = metrics_from_rows(rows)

    assert metrics["meetings"] == 2
    assert metrics["dials"] == 40
    assert metrics["connect_percent"] == 25
    assert metrics["deals_created"] == 3
    assert metrics["kp_sent"] == 1


def test_metric_delta_formats_percent_and_absence():
    assert metric_delta(7, 4)["delta_percent"] == 75
    assert delta_label(metric_delta(7, 4)) == "+75%"
    assert metric_delta(7, None)["delta"] is None


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.calls.append((sql, params))

    def fetchone(self):
        return self.conn.rows.pop(0)


class Conn:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def cursor(self):
        return Cursor(self)


def test_compute_deltas_uses_previous_report_date():
    conn = Conn(
        [
            (date(2026, 6, 1),),
            (4, 100, 20, 1, 2),
        ]
    )
    rows = {
        "meetings": [{"meeting_id": i} for i in range(7)],
        "kp_briefs": [{"item_type": "kp"} for _ in range(3)],
        "manager_activity": [{"dials_total": 175, "calls_answered": 35, "deals_created_count": 2}],
    }

    out = compute_deltas(conn, date(2026, 6, 2), rows)

    assert out["previous_report_date"] == "2026-06-01"
    assert out["metrics"]["meetings"]["delta_percent"] == 75
    assert out["metrics"]["dials"]["delta"] == 75


def test_compute_deltas_without_previous_keeps_null_delta():
    out = compute_deltas(Conn([(None,)]), date(2026, 6, 2), {"meetings": [], "manager_activity": [], "kp_briefs": []})

    assert out["previous_report_date"] is None
    assert out["metrics"]["meetings"]["delta"] is None
