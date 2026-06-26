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


class GuardClient(BitrixClient):
    """Клиент с замоканной сетью — проверяем предохранитель удаления."""

    def __init__(self):
        self.network_calls: list[tuple[str, dict]] = []

    def _ensure_fresh_state(self):
        return None

    def _log_call(self, *args, **kwargs):
        return None

    def _call_with_retries(self, method, params):
        self.network_calls.append((method, params))
        return {"result": True}


def test_delete_blocked_by_default(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    bx = GuardClient()
    for method in ("crm.contact.delete", "crm.company.delete", "crm.deal.delete", "crm.lead.delete"):
        body = bx.call(method, {"id": "1"})
        assert body["result"] is False
        assert body["error"] == "DELETE_BLOCKED"
    # ни один delete не ушёл в сеть
    assert bx.network_calls == []


def test_unbind_relations_not_blocked(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    bx = GuardClient()
    bx.call("crm.deal.contact.delete", {"id": "1", "fields": {"CONTACT_ID": 2}})
    bx.call("crm.contact.company.delete", {"id": "1", "fields": {"COMPANY_ID": 2}})
    # unbind-методы проходят как обычно
    assert [m for m, _ in bx.network_calls] == [
        "crm.deal.contact.delete",
        "crm.contact.company.delete",
    ]


def test_delete_allowed_with_env(monkeypatch):
    monkeypatch.setenv("BITRIX_ALLOW_DELETE", "1")
    bx = GuardClient()
    body = bx.call("crm.contact.delete", {"id": "1"})
    assert body == {"result": True}
    assert bx.network_calls == [("crm.contact.delete", {"id": "1"})]
