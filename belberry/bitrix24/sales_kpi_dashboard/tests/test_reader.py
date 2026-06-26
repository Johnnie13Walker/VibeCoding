from __future__ import annotations

import re
from datetime import date
from unittest.mock import Mock

from sales_kpi_dashboard.reader import BitrixReader


def test_resolve_role_users_filters_by_regex() -> None:
    client = Mock()
    client.call.side_effect = [
        {
            "result": [
                {"ID": "2772", "NAME": "Дарья", "LAST_NAME": "Исаева", "WORK_POSITION": "Телемаркетолог"},
                {"ID": "2832", "NAME": "Аркадий", "LAST_NAME": "Вострецов", "WORK_POSITION": "телемаркетолог"},
                {"ID": "2806", "NAME": "Елизавета", "LAST_NAME": "Деговцова", "WORK_POSITION": "Менеджер по продажам"},
                {"ID": "584", "NAME": "Екатерина", "LAST_NAME": "Смирнова", "WORK_POSITION": "Аккаунт-менеджер"},
            ]
        }
    ]
    reader = BitrixReader(client)

    assert reader.resolve_role_users(re.compile("телемарк", re.IGNORECASE)) == {
        2772: "Исаева Дарья",
        2832: "Вострецов Аркадий",
    }


def test_resolve_role_users_includes_sales_rop_via_mop_regex() -> None:
    from sales_kpi_dashboard import config

    client = Mock()
    client.call.side_effect = [
        {
            "result": [
                {"ID": "2806", "NAME": "Елизавета", "LAST_NAME": "Деговцова",
                 "WORK_POSITION": "Менеджер по продажам"},
                {"ID": "2846", "NAME": "Егор", "LAST_NAME": "Семенихин",
                 "WORK_POSITION": "Менеджер по продажам"},
                {"ID": "2188", "NAME": "Евгения", "LAST_NAME": "Гордиенко",
                 "WORK_POSITION": "РОП"},
                {"ID": "470", "NAME": "Мария", "LAST_NAME": "Лопатина",
                 "WORK_POSITION": "Руководитель отдела аккаунтинга"},
                {"ID": "584", "NAME": "Екатерина", "LAST_NAME": "Смирнова",
                 "WORK_POSITION": "Аккаунт-менеджер"},
            ]
        }
    ]
    reader = BitrixReader(client)
    users = reader.resolve_role_users(config.MOP_POSITION_REGEX)

    # МОП и РОП-продавец должны попасть
    assert users == {
        2188: "Гордиенко Евгения",
        2806: "Деговцова Елизавета",
        2846: "Семенихин Егор",
    }


def test_list_active_users_paginates() -> None:
    client = Mock()
    client.call.side_effect = [
        {"result": [{"ID": str(i)} for i in range(1, 51)], "next": 50},
        {"result": [{"ID": str(i)} for i in range(51, 101)], "next": 100},
        {"result": [{"ID": str(i)} for i in range(101, 151)]},
    ]
    reader = BitrixReader(client)

    rows = reader.list_active_users()

    assert len(rows) == 150
    assert client.call.call_args_list[0].args[1]["start"] == 0
    assert client.call.call_args_list[1].args[1]["start"] == 50
    assert client.call.call_args_list[2].args[1]["start"] == 100


def test_productrows_for_deals_batches() -> None:
    client = Mock()
    client.call.side_effect = [
        {
            "result": {
                "result": {
                    str(deal_id): [
                        {"OWNER_ID": str(deal_id), "PRODUCT_ID": "7658", "PRICE": "100", "QUANTITY": "1"}
                    ]
                    for deal_id in range(1, 51)
                }
            }
        },
        {
            "result": {
                "result": {
                    str(deal_id): [
                        {"OWNER_ID": str(deal_id), "PRODUCT_ID": "7658", "PRICE": "100", "QUANTITY": "1"}
                    ]
                    for deal_id in range(51, 101)
                }
            }
        },
    ]
    reader = BitrixReader(client)

    rows = reader.productrows_for_deals(list(range(1, 101)))

    assert len(rows) == 100
    assert client.call.call_count == 2
    assert client.call.call_args_list[0].args[0] == "batch"


def test_count_tasks_closed_paginates() -> None:
    client = Mock()
    client.call.side_effect = [
        {"result": {"tasks": [{"ID": str(i)} for i in range(50)]}, "next": 50},
        {"result": {"tasks": [{"ID": str(i)} for i in range(50, 75)]}},
    ]
    reader = BitrixReader(client)

    assert reader.count_tasks_closed(2806, date(2026, 5, 1)) == 75


def test_list_meetings_in_period_includes_meeting_smart_process() -> None:
    client = Mock()
    client.paginate_by_start.return_value = []
    client.call.return_value = {
        "result": {
            "items": [
                {
                    "id": 2030,
                    "title": "aclinic.ru (Бриффинг)",
                    "createdBy": 2832,
                    "assignedById": 2822,
                    "stageId": "DT1048_24:SUCCESS",
                    "ufCrm16_1751009238": "2026-05-05T14:00:00+03:00",
                    "parentId2": 14652,
                }
            ]
        }
    }
    reader = BitrixReader(client)

    rows = reader.list_meetings_in_period(date(2026, 5, 1), date(2026, 5, 20))

    assert rows == [
        {
            "ID": "SP1048:2030",
            "SUBJECT": "aclinic.ru (Бриффинг)",
            "OWNER_ID": 14652,
            "OWNER_TYPE_ID": "2",
            "DEAL_ID": 14652,
            "COMPANY_ID": 0,
            "COMPLETED": "Y",
            "CREATED": "2026-05-05T14:00:00+03:00",
            "CREATED_BY_ID": 2832,
            "RESPONSIBLE_ID": 2822,
        }
    ]
