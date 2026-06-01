import json
from datetime import date, datetime
from pathlib import Path

from src.render import SECTION_H2_MARKERS, extract_rejections, render_report
from src.timeutil import MSK
from src.transform import build_db_rows, compute_stale_deals

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "2026-05-29"
NOW = datetime(2026, 5, 30, 9, 0, tzinfo=MSK)


def load_raw():
    raw = json.loads((FIXTURE_DIR / "raw.json").read_text())
    raw["calls"] = json.loads((FIXTURE_DIR / "vox.json").read_text())
    raw["users"] = json.loads((FIXTURE_DIR / "users.json").read_text())
    raw["photos"] = json.loads((FIXTURE_DIR / "photos.json").read_text())
    raw.setdefault("wazzup", {})
    raw.setdefault("report_date", "2026-05-29")
    return raw


def render_fixture():
    raw = load_raw()
    rows = build_db_rows(raw, date(2026, 5, 29), NOW)
    extras = {
        "raw": raw,
        "report_date": "2026-05-29",
        "stale": compute_stale_deals(raw["deals_open"], NOW, raw.get("wazzup")),
        "users": raw["users"],
        "photos": raw["photos"],
        "rejections": extract_rejections(raw, raw["users"]),
    }
    return render_report(rows, extras)


def test_render_has_all_13_sections_in_order():
    output = render_fixture()

    indexes = [output.index(marker) for marker in SECTION_H2_MARKERS]

    assert indexes == sorted(indexes)
    assert len(indexes) == 13


def test_render_contains_reference_structure_links_doctype_and_style():
    output = render_fixture()

    assert output.startswith("<!DOCTYPE html>")
    assert "<style>" in output
    assert "/crm/deal/details/" in output
    assert "/crm/type/1048/details/" in output
    assert "data-llm-placeholder" in output
    assert "официальная сводка «Опер» недоступна" in output


def test_rejections_include_apology_and_exclude_telemarketing_lose():
    raw = {
        "stagehistory": [
            {"OWNER_ID": 1, "STAGE_ID": "C50:LOSE", "STAGE_SEMANTIC_ID": "F"},
            {"OWNER_ID": 2, "STAGE_ID": "C50:APOLOGY", "STAGE_SEMANTIC_ID": "F"},
            {"OWNER_ID": 3, "STAGE_ID": "C10:LOSE", "STAGE_SEMANTIC_ID": "F"},
        ],
        "deals_created": [
            {"ID": "1", "TITLE": "Отложено", "ASSIGNED_BY_ID": "10"},
            {"ID": "2", "TITLE": "Отвал ТМ", "ASSIGNED_BY_ID": "10"},
            {"ID": "3", "TITLE": "Отвал Продажи", "ASSIGNED_BY_ID": "10"},
        ],
        "deals_open": [],
    }

    rejections = extract_rejections(raw, {"10": "Менеджер Тест"})

    assert [item["deal_id"] for item in rejections] == ["2", "3"]
    assert all(item["stage"] != "C50:LOSE" for item in rejections)


def test_stale_deal_title_is_rendered_as_link_text():
    output = render_fixture()

    assert "sporttravma.org" in output or "newflat.ai" in output
    assert "<a href=\"https://belberrycrm.bitrix24.ru/crm/deal/details/" in output
