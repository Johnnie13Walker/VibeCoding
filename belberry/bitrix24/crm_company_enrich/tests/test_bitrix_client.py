from __future__ import annotations

from crm_company_enrich.bitrix_client import BitrixClient


class FakeBitrixClient(BitrixClient):
    def __init__(self, deals):
        self.deals = deals
        self.paginate_calls = []

    def paginate(self, method: str, params: dict, id_field: str = "ID"):
        self.paginate_calls.append((method, params, id_field))
        yield from self.deals


def test_list_company_deals_uses_paginate_and_returns_more_than_50_rows():
    deals = [{"ID": str(i), "COMPANY_ID": "10"} for i in range(1, 76)]
    bx = FakeBitrixClient(deals)

    result = bx.list_company_deals("10")

    assert len(result) == 75
    assert result[0]["ID"] == "1"
    assert result[-1]["ID"] == "75"
    assert bx.paginate_calls[0][0] == "crm.deal.list"
    assert bx.paginate_calls[0][1]["filter"] == {"COMPANY_ID": "10"}
