from src.sync_deal_titles import build_title_rows


def test_build_title_rows_maps_id_title():
    rows = build_title_rows(
        [
            {"ID": "24430", "TITLE": "baikal-smile.ru"},
            {"ID": 100, "TITLE": None},
            {"TITLE": "без id"},  # пропуск
        ]
    )
    assert len(rows) == 2
    assert rows[0] == {"deal_id": 24430, "title": "baikal-smile.ru"}
    assert rows[1] == {"deal_id": 100, "title": None}
