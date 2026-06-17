from datetime import date

from src import sync_absences as A


def test_date_head_parses_hr_and_iso():
    assert A._date_head("05.06.2026 00:00:00") == date(2026, 6, 5)
    assert A._date_head("2026-06-05") == date(2026, 6, 5)
    assert A._date_head("") is None


def test_kind_classifies_by_name():
    assert A._kind("Больничный лист") == "больничный"
    assert A._kind("Отгул") == "отгул"
    assert A._kind("Командировка в Москву") == "командировка"
    assert A._kind("Ежегодный отпуск") == "отпуск"


class _FakeBx:
    def __init__(self, result): self._result = result
    def call(self, method, params): return {"result": self._result}


def test_fetch_absence_days_expands_period_weekdays_in_window():
    bx = _FakeBx({"2806": [{"FROM_HR": True, "NAME": "Отпуск", "DT_FROM": "03.06.2026", "DT_TO": "08.06.2026"}]})
    days = A.fetch_absence_days(date(2026, 6, 1), date(2026, 6, 30), [2806], bx)
    got = sorted(d for (uid, d) in days.keys())
    assert got == ["2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08"]
    assert all(v == "отпуск" for v in days.values())


def test_fetch_absence_days_ignores_non_absence_events():
    bx = _FakeBx({"1": [{"NAME": "Встреча с клиентом", "DT_FROM": "03.06.2026", "DT_TO": "03.06.2026"}]})
    assert A.fetch_absence_days(date(2026, 6, 1), date(2026, 6, 30), [1], bx) == {}
