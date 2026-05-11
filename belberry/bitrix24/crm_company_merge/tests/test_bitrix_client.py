from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs

import pytest

from crm_company_merge import bitrix_client
from crm_company_merge.bitrix_client import BitrixClient, BitrixRateLimited


class FakeResponse:
    def __init__(self, body: dict[str, Any]):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    path = tmp_path / "install.latest.json"
    write_state(path, expires=int(time.time()) + 3600)
    return path


def write_state(path: Path, expires: int, token: str = "token") -> None:
    path.write_text(
        json.dumps(
            {
                "payload": {
                    "auth[client_endpoint]": "https://example.bitrix24.ru/rest/",
                    "auth[access_token]": token,
                    "auth[expires]": expires,
                }
            }
        ),
        encoding="utf-8",
    )


def install_urlopen(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout=30):
        calls.append(
            {
                "url": request.full_url,
                "data": parse_qs(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr(bitrix_client.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_call_success(state_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "bitrix.csv"
    calls = install_urlopen(monkeypatch, [{"result": {"ID": "1"}}])

    body = BitrixClient(state_path, log_path=log_path).call("crm.company.get", {"id": "1"})

    assert body == {"result": {"ID": "1"}}
    assert calls[0]["url"] == "https://example.bitrix24.ru/rest/crm.company.get.json"
    assert calls[0]["data"]["auth"] == ["token"]
    assert calls[0]["data"]["id"] == ["1"]
    log_line = log_path.read_text(encoding="utf-8").strip()
    assert "crm.company.get" in log_line
    assert ",1," in log_line


def test_call_retries_on_query_limit(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_urlopen(
        monkeypatch,
        [
            {"error": "QUERY_LIMIT_EXCEEDED", "error_description": "Too many requests"},
            {"result": {"ok": True}},
        ],
    )
    monkeypatch.setattr(bitrix_client.time, "sleep", lambda delay: None)

    body = BitrixClient(state_path).call("profile")

    assert body == {"result": {"ok": True}}
    assert len(calls) == 2


def test_call_retries_on_5xx(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    http_503 = HTTPError("https://example", 503, "Service unavailable", hdrs=None, fp=None)
    calls = install_urlopen(monkeypatch, [http_503, {"result": ["ok"]}])
    monkeypatch.setattr(bitrix_client.time, "sleep", lambda delay: None)

    body = BitrixClient(state_path).call("crm.company.list")

    assert body == {"result": ["ok"]}
    assert len(calls) == 2


def test_call_fails_after_max_retries(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_urlopen(
        monkeypatch,
        [{"error": "QUERY_LIMIT_EXCEEDED", "error_description": "Too many requests"}] * 4,
    )
    monkeypatch.setattr(bitrix_client.time, "sleep", lambda delay: None)

    with pytest.raises(BitrixRateLimited):
        BitrixClient(state_path).call("profile")

    assert len(calls) == 4


def test_get_company_returns_none_on_not_found(
    state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_urlopen(monkeypatch, [{"error": "", "error_description": "Not found"}])

    company = BitrixClient(state_path).get_company("404")

    assert company is None


def test_batch_chunks_above_50(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_urlopen(
        monkeypatch,
        [
            {"result": {"result": {f"cmd_{i}": {"ID": str(i)} for i in range(50)}}},
            {"result": {"result": {f"cmd_{i}": {"ID": str(i)} for i in range(50, 100)}}},
            {"result": {"result": {f"cmd_{i}": {"ID": str(i)} for i in range(100, 120)}}},
        ],
    )
    commands = {f"cmd_{i}": ("crm.company.get", {"id": str(i)}) for i in range(120)}

    result = BitrixClient(state_path).batch(commands)

    assert len(calls) == 3
    assert len(result) == 120
    assert "cmd[cmd_0]" in calls[0]["data"]
    assert len([key for key in calls[0]["data"] if key.startswith("cmd[")]) == 50


def test_paginate_yields_all_pages(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = []
    for page in range(3):
        responses.append({"result": [{"ID": str(page * 50 + i + 1)} for i in range(50)]})
    responses.append({"result": []})
    calls = install_urlopen(monkeypatch, responses)

    rows = list(BitrixClient(state_path).paginate("crm.company.list", {"filter": {"TITLE": "A"}}))

    assert len(rows) == 150
    assert rows[0]["ID"] == "1"
    assert rows[-1]["ID"] == "150"
    assert calls[0]["data"]["filter[>ID]"] == ["0"]
    assert calls[1]["data"]["filter[>ID]"] == ["50"]
    assert "start" in calls[0]["data"]
    assert "next" not in calls[0]["data"]


def test_state_expired_triggers_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "install.latest.json"
    write_state(state, expires=1, token="old-token")
    sync_script = tmp_path / "bitrix-sync-state.sh"
    sync_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fake_run(command, check):
        assert command == [str(sync_script)]
        assert check is True
        write_state(state, expires=int(time.time()) + 3600, token="new-token")

    calls = install_urlopen(monkeypatch, [{"result": {"ok": True}}])
    monkeypatch.setattr(bitrix_client, "SYNC_SCRIPT", sync_script)
    monkeypatch.setattr(bitrix_client.subprocess, "run", fake_run)

    body = BitrixClient(state).call("profile")

    assert body == {"result": {"ok": True}}
    assert calls[0]["data"]["auth"] == ["new-token"]
