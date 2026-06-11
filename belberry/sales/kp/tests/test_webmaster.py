"""Тесты Вебмастер-модуля (pure, без сети)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webmaster_audit import quick_wins, render_webmaster_rows  # noqa: E402

QUERIES = [
    {"query_text": "радиогид купить", "indicators":
        {"AVG_SHOW_POSITION": 6.2, "TOTAL_SHOWS": 420, "TOTAL_CLICKS": 12}},
    {"query_text": "crystal sound", "indicators":
        {"AVG_SHOW_POSITION": 1.1, "TOTAL_SHOWS": 900, "TOTAL_CLICKS": 300}},  # уже топ
    {"query_text": "аудиогид аренда", "indicators":
        {"AVG_SHOW_POSITION": 11.0, "TOTAL_SHOWS": 15, "TOTAL_CLICKS": 0}},    # мало показов
    {"query_text": "радиогид для экскурсий", "indicators":
        {"AVG_SHOW_POSITION": 9.4, "TOTAL_SHOWS": 210, "TOTAL_CLICKS": 3}},
]


def test_quick_wins_filters_position_and_demand():
    wins = quick_wins(QUERIES)
    assert [w["query"] for w in wins] == ["радиогид купить", "радиогид для экскурсий"]
    assert wins[0]["position"] == 6.2 and wins[0]["shows"] == 420


def test_render_rows_format_and_empty():
    rows = render_webmaster_rows({"quick_wins": quick_wins(QUERIES)})
    assert 'class="metric"' in rows and "радиогид купить" in rows and "топ-3" in rows
    assert render_webmaster_rows({"quick_wins": []}) is None
