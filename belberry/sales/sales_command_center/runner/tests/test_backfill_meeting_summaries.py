from src import backfill_meeting_summaries as B


def test_post_meeting_text_filters_before_meeting():
    mt = "2026-06-10T12:00:00+03:00"
    wz = [
        {"CREATED": "2026-06-10T09:00:00+03:00", "COMMENT": "до встречи — не считаем"},
        {"CREATED": "2026-06-10T15:00:00+03:00", "COMMENT": "Елизавета: итоги встречи, договорились по КП"},
        {"CREATED": "2026-06-12T10:00:00+03:00", "COMMENT": "клиент: ок, жду"},
    ]
    text = B._post_meeting_text(mt, wz)
    assert "до встречи" not in text
    assert "итоги встречи" in text
    assert "жду" in text


def test_post_meeting_text_empty_when_only_before():
    mt = "2026-06-10T12:00:00+03:00"
    wz = [{"CREATED": "2026-06-10T09:00:00+03:00", "COMMENT": "только до встречи"}]
    assert B._post_meeting_text(mt, wz).strip() == ""
