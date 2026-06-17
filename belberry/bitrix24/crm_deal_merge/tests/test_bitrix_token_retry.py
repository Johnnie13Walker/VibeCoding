from __future__ import annotations

from urllib.error import HTTPError

from crm_deal_merge.bitrix_client import BitrixClient


def test_http_401_syncs_state_and_retries(monkeypatch) -> None:
    client = object.__new__(BitrixClient)
    client._last_sync_at_monotonic = 0.0
    calls = {"post": 0, "sync": 0}

    def fake_post(method: str, params: dict):
        calls["post"] += 1
        if calls["post"] == 1:
            raise HTTPError("https://example.test", 401, "Unauthorized", {}, None)
        return {"result": {"ok": True}}

    def fake_sync():
        calls["sync"] += 1

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client, "_sync_state", fake_sync)

    result = client._call_with_retries("crm.company.list", {})

    assert result == {"result": {"ok": True}}
    assert calls == {"post": 2, "sync": 1}
