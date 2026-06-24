from src.feed import build_day_feed, extract_rejections


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


def test_extract_rejections_uses_rejected_deal_titles():
    raw = {
        "stagehistory": [{"OWNER_ID": "14652", "STAGE_ID": "C10:LOSE"}],
        "deals_created": [],
        "deals_open": [],
        "rejected_deals": [{"ID": "14652", "TITLE": "aclinic.ru", "ASSIGNED_BY_ID": "10"}],
        "users": {"10": "Семенихин Егор"},
    }
    out = extract_rejections(raw, raw["users"])
    assert out[0]["title"] == "aclinic.ru"  # домен, а не «Сделка 14652»
    assert out[0]["manager"] == "Семенихин Егор"


def test_build_day_feed_scopes_and_excludes_spam():
    raw = {
        "user_roles": {"10": "Менеджер по продажам", "20": "Телемаркетолог", "99": "Рекрутер"},
        "meet_day": [{"assignedById": 10, "title": "kandela.ru", "ufCrm16_1751009238": "2026-06-04T10:00:00"}],
        "briefs": [{"assignedById": 20, "title": "rant.ru", "createdTime": "2026-06-04T11:00:00"}],
        "kp": [{"assignedById": 99, "title": "hr.ru", "updatedTime": "2026-06-04T12:00:00"}],  # HR — вне скоупа
        "deals_created": [
            {"ASSIGNED_BY_ID": 10, "TITLE": "real.ru", "DATE_CREATE": "2026-06-04T13:00:00"},
            {"ASSIGNED_BY_ID": 10, "TITLE": "spam.ru", "DATE_CREATE": "2026-06-04T14:00:00", "UF_CRM_1771495464": "8588"},
        ],
    }
    feed = build_day_feed(raw)
    titles = [e["title"] for e in feed]
    assert "kandela.ru" in titles and "rant.ru" in titles and "real.ru" in titles
    assert "hr.ru" not in titles  # рекрутёр вне ОП+ТМ
    assert "spam.ru" not in titles  # спам-сделка исключена
    assert feed[0]["at"] >= feed[-1]["at"]  # сортировка по времени убыв.
