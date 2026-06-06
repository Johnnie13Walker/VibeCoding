from src.transform import _meeting_type


def test_type_from_structural_field():
    # 2638 = брифинг, 2640 = защита — даже если название это домен клиента.
    assert _meeting_type({"ufCrm16_1751006460": 2638, "title": "client.ru"}) == "briefing"
    assert _meeting_type({"ufCrm16_1751006460": "2640", "title": "client.ru"}) == "defense"


def test_fallback_to_title_when_field_empty():
    assert _meeting_type({"ufCrm16_1751006460": None, "title": "site.ru (Защита)"}) == "defense"
    assert _meeting_type({"title": "site.ru (Брифинг)"}) == "briefing"


def test_other_when_no_field_and_plain_domain():
    # Поле пустое/нестандартное (2644/8596) + название-домен → «другое».
    assert _meeting_type({"ufCrm16_1751006460": 2644, "title": "client.ru"}) == "other"
    assert _meeting_type({"title": "client.ru"}) == "other"
