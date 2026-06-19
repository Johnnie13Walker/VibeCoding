from datetime import date

from src import sync_wins as sw
from src.sync_wins import build_win_rows, fetch_won_dates


def test_build_win_rows_maps_amount_owner_and_date():
    deals = [
        {"ID": 100, "ASSIGNED_BY_ID": 2806, "TITLE": "amoriya.ru", "OPPORTUNITY": "250000"},
        {"ID": 200, "ASSIGNED_BY_ID": 686, "TITLE": "med.ru", "OPPORTUNITY": None},
    ]
    won_dates = {100: "2026-06-10T14:00:00+03:00", 200: "2026-05-01T09:00:00+03:00"}
    owners = {
        2806: {"name": "Семенихин Егор", "dept": "Менеджер по продажам", "active": True},
        686: {"name": "Дудин Петр", "dept": "Менеджер по продажам", "active": False},  # уволен
    }
    rows = {r["deal_id"]: r for r in build_win_rows(deals, won_dates, owners)}

    assert rows[100]["opportunity"] == 250000.0
    assert rows[100]["won_date"] == date(2026, 6, 10)
    assert rows[100]["owner_name"] == "Семенихин Егор" and rows[100]["owner_active"] is True
    # уволенный владелец сохраняется (денормализация), сумма пустая → None, не падаем
    assert rows[200]["owner_active"] is False
    assert rows[200]["opportunity"] is None


def test_fetch_won_dates_dedups_to_latest_transition():
    def fake_fetch_all(bx, method, params):
        assert method == "crm.stagehistory.list"
        return [
            {"OWNER_ID": 100, "CREATED_TIME": "2026-03-01T10:00:00+03:00", "STAGE_ID": "C10:WON"},
            {"OWNER_ID": 100, "CREATED_TIME": "2026-06-10T10:00:00+03:00", "STAGE_ID": "C10:WON"},
        ]

    orig = sw._fetch_all
    sw._fetch_all = fake_fetch_all
    try:
        out = fetch_won_dates(object(), "2026-01-01")
    finally:
        sw._fetch_all = orig
    assert out[100] == "2026-06-10T10:00:00+03:00"  # последний переход
