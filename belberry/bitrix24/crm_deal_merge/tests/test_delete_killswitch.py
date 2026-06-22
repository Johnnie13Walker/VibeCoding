from __future__ import annotations

from crm_deal_merge.bitrix_client import BitrixClient


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


def test_company_delete_blocked_by_default(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    bx = GuardClient()
    for method in ("crm.company.delete", "crm.contact.delete", "crm.deal.delete", "crm.lead.delete"):
        body = bx.call(method, {"id": "1"})
        assert body["result"] is False
        assert body["error"] == "DELETE_BLOCKED"
    assert bx.network_calls == []


def test_unbind_relations_not_blocked(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    bx = GuardClient()
    bx.call("crm.deal.contact.delete", {"id": "1", "fields": {"CONTACT_ID": 2}})
    assert [m for m, _ in bx.network_calls] == ["crm.deal.contact.delete"]


def test_delete_allowed_with_env(monkeypatch):
    monkeypatch.setenv("BITRIX_ALLOW_DELETE", "1")
    bx = GuardClient()
    body = bx.call("crm.company.delete", {"id": "1"})
    assert body == {"result": True}
    assert bx.network_calls == [("crm.company.delete", {"id": "1"})]
