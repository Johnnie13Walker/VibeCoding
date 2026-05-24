from pathlib import Path

from crm_deal_merge import sheets_client
from crm_deal_merge.sheets_client import SheetsClient


def test_sheets_client_timeout_configured(monkeypatch):
    calls = {}

    class _FakeCredentials:
        @staticmethod
        def from_service_account_file(path, scopes):
            calls["credentials_path"] = path
            calls["scopes"] = scopes
            return "credentials"

    class _FakeHttp:
        def __init__(self, timeout):
            calls["timeout"] = timeout

    def fake_authorized_http(credentials, http):
        calls["authorized_credentials"] = credentials
        calls["authorized_http"] = http
        return "authorized-http"

    def fake_build(api, version, http):
        calls["api"] = api
        calls["version"] = version
        calls["build_http"] = http
        return object()

    monkeypatch.setattr(sheets_client, "Credentials", _FakeCredentials)
    monkeypatch.setattr(sheets_client.httplib2, "Http", _FakeHttp)
    monkeypatch.setattr(sheets_client, "AuthorizedHttp", fake_authorized_http)
    monkeypatch.setattr(sheets_client, "build", fake_build)

    SheetsClient("sheet-id", Path("/tmp/fake-service-account.json"))

    assert calls["timeout"] == 60
    assert calls["authorized_credentials"] == "credentials"
    assert calls["build_http"] == "authorized-http"
    assert calls["api"] == "sheets"
    assert calls["version"] == "v4"
