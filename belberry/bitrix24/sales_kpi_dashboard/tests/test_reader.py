from __future__ import annotations

import re
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
