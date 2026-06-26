from __future__ import annotations

import json
import urllib.request

from empty_companies_score.bitrix_client import BitrixClient


class _Client(BitrixClient):
    """Клиент без чтения state-файла — проверяем предохранитель удаления."""

    def __init__(self):
        self.endpoint = "https://example.invalid"
        self.token = "tok"


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_network(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(req, *a, **k):
        calls.append(req.full_url)
        return _FakeResp({"result": True})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_company_delete_blocked_by_default(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    calls = _patch_network(monkeypatch)
    bx = _Client()
    for method in ("crm.company.delete", "crm.contact.delete", "crm.deal.delete", "crm.lead.delete"):
        body = bx.call(method, [("id", "1")])
        assert body["result"] is False
        assert body["error"] == "DELETE_BLOCKED"
    assert calls == []  # сеть не дёрнута ни разу


def test_unbind_relations_not_blocked(monkeypatch):
    monkeypatch.delenv("BITRIX_ALLOW_DELETE", raising=False)
    calls = _patch_network(monkeypatch)
    bx = _Client()
    body = bx.call("crm.deal.contact.delete", [("id", "1")])
    assert body == {"result": True}
    assert len(calls) == 1


def test_delete_allowed_with_env(monkeypatch):
    monkeypatch.setenv("BITRIX_ALLOW_DELETE", "1")
    calls = _patch_network(monkeypatch)
    bx = _Client()
    body = bx.call("crm.company.delete", [("id", "1")])
    assert body == {"result": True}
    assert len(calls) == 1
