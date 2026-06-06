from src.chat_attribution import (
    attribute_dialogs,
    build_employee_index,
    match_sender,
    parse_sender,
)

# Реальные форматы тел Wazzup-сообщений (из live-пробы Bitrix).
OUT_SEMENIKHIN = "[img]https://static.wazzup24.com/images/bitrix/max.png[/img]&nbsp; Егор Семенихин: Алексей, это Егор, Belberry :f09f918b: Прошу скинуть ИНН"
IN_CLIENT = "[img]https://static.wazzup24.com/images/bitrix/whatsapp.png[/img]&nbsp; Эдвин Линго: Да давайте в 13"
SERVICE = "[img]https://static.wazzup24.com/images/bitrix/whatsapp.png[/img]&nbsp; Телефон: Кира, добрый день"


def test_parse_sender_strips_markup_and_emoji():
    assert parse_sender(OUT_SEMENIKHIN) == "Егор Семенихин"
    assert parse_sender(IN_CLIENT) == "Эдвин Линго"
    assert parse_sender(SERVICE) == "Телефон"
    assert parse_sender("") is None
    assert parse_sender("без двоеточия вовсе") is None


# Справочник «Фамилия Имя» (как user.get LAST_NAME + NAME).
EMP = {"2814": "Семенихин Егор", "2846": "Гордиенко Евгения", "555": "Исаева Дарья", "999": "Анна"}
INDEX = build_employee_index(EMP)


def test_index_drops_single_token_names():
    # «Анна» (один токен) не попадает — иначе ложные совпадения с клиентами.
    assert all("999" != emp_id for emp_id, _ in INDEX)
    assert len(INDEX) == 3


def test_match_sender_order_insensitive_unique():
    assert match_sender("Егор Семенихин", INDEX) == "2814"  # порядок Имя↔Фамилия не важен
    assert match_sender("Исаева Дарья", INDEX) == "555"
    assert match_sender("Эдвин Линго", INDEX) is None  # клиент
    assert match_sender("Телефон", INDEX) is None  # служебная подпись
    assert match_sender("Анна", INDEX) is None  # один токен


def test_attribute_dialogs_counts_distinct_deals_per_manager():
    wazzup = {
        # сделка 1: Семенихин писал дважды за день → 1 диалог
        "1": [
            {"CREATED": "2026-06-05T10:00:00+03:00", "COMMENT": OUT_SEMENIKHIN},
            {"CREATED": "2026-06-05T12:00:00+03:00", "COMMENT": OUT_SEMENIKHIN},
            {"CREATED": "2026-06-05T12:30:00+03:00", "COMMENT": IN_CLIENT},  # клиент — не считаем
        ],
        # сделка 2: Семенихин + Исаева в один день → каждому по диалогу
        "2": [
            {"CREATED": "2026-06-05T09:00:00+03:00", "COMMENT": OUT_SEMENIKHIN},
            {"CREATED": "2026-06-05T15:00:00+03:00", "COMMENT": "Исаева Дарья: добрый день"},
        ],
        # сделка 3: сообщение в другой день → не в окне
        "3": [{"CREATED": "2026-06-04T09:00:00+03:00", "COMMENT": OUT_SEMENIKHIN}],
    }
    d0, d1 = "2026-06-05T00:00:00+03:00", "2026-06-05T23:59:59+03:00"
    counts = attribute_dialogs(wazzup, EMP, d0, d1)
    assert counts == {"2814": 2, "555": 1}


def test_attribute_dialogs_empty():
    assert attribute_dialogs({}, EMP, "2026-06-05T00:00:00+03:00", "2026-06-05T23:59:59+03:00") == {}
    assert attribute_dialogs(None, EMP, "a", "b") == {}
