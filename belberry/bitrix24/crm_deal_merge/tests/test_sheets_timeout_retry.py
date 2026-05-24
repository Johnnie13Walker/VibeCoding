from __future__ import annotations

import socket

import pytest

from crm_deal_merge.sheets_client import SheetsClient


class FakeRequest:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def execute(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("[Errno 60] Operation timed out")
        return {"ok": True}


def test_sheets_timeout_retry_succeeds(monkeypatch):
    monkeypatch.setattr("crm_deal_merge.sheets_client.time.sleep", lambda _: None)
    client = object.__new__(SheetsClient)
    request = FakeRequest(failures=2)

    result = client._execute_with_retry(request)

    assert result == {"ok": True}
    assert request.calls == 3


def test_sheets_timeout_retry_exhausted(monkeypatch):
    monkeypatch.setattr("crm_deal_merge.sheets_client.time.sleep", lambda _: None)
    client = object.__new__(SheetsClient)
    request = FakeRequest(failures=4)

    with pytest.raises(TimeoutError):
        client._execute_with_retry(request)

    assert request.calls == 4


def test_sheets_transient_dns_retry_succeeds(monkeypatch):
    monkeypatch.setattr("crm_deal_merge.sheets_client.time.sleep", lambda _: None)
    client = object.__new__(SheetsClient)

    class FakeDnsRequest:
        calls = 0

        def execute(self):
            self.calls += 1
            if self.calls == 1:
                raise socket.gaierror(8, "nodename nor servname provided, or not known")
            return {"ok": True}

    request = FakeDnsRequest()

    result = client._execute_with_retry(request)

    assert result == {"ok": True}
    assert request.calls == 2
