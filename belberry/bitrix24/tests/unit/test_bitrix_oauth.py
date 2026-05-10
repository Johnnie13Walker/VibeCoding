from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from unittest.mock import patch

from belberry.bitrix24.providers import bitrix_oauth as oauth
from belberry.bitrix24.providers.bitrix_oauth import (
    BitrixAppState,
    BitrixHttpRequest,
    BitrixHttpResponse,
    BitrixOAuth,
    BitrixOAuthError,
)
from belberry.bitrix24.providers.logging import sanitize_bitrix_text


class FakeTransport:
    def __init__(self, responses=None, exc: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.exc = exc
        self.requests: list[BitrixHttpRequest] = []
        self.timeouts: list[int] = []

    def __call__(self, request: BitrixHttpRequest, timeout_sec: int) -> BitrixHttpResponse:
        self.requests.append(request)
        self.timeouts.append(timeout_sec)
        if self.exc is not None:
            raise self.exc
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


class FakeResponse:
    status = 200

    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.body


class BitrixOAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir = Path(self.tmp.name) / "state"
        self.state_dir.mkdir()
        self.state_path = self.state_dir / "install.latest.json"

    def write_state(self, *, name: str = "install.latest.json", saved_at: str = "2026-05-10T09:30:00+03:00", **payload):
        record = {
            "saved_at": saved_at,
            "payload": {
                "auth[access_token]": "access-token-123456",
                "auth[refresh_token]": "refresh-token-123456",
                "auth[client_endpoint]": "https://portal.example/rest",
                "auth[server_endpoint]": "https://portal.example",
                "auth[domain]": "portal.example",
                "auth[member_id]": "member-1",
                "auth[status]": "L",
                **payload,
            },
            "summary": {},
        }
        path = self.state_dir / name
        path.write_text(json.dumps(record), encoding="utf-8")
        self.state_path = path
        return path

    def make_auth(self, *, transport=None, sleep=None, state_file=None) -> BitrixOAuth:
        return BitrixOAuth(
            state_dir=self.state_dir,
            state_file=state_file,
            client_id="client-id",
            client_secret="client-secret",
            transport=transport or FakeTransport([BitrixHttpResponse(200, "{}")]),
            sleep=sleep or (lambda _: None),
        )

    def test_from_env_uses_only_belberry_namespace(self) -> None:
        transport = FakeTransport([])

        auth = BitrixOAuth.from_env(
            {
                "BELBERRY_BITRIX24_APP_STATE_DIR": str(self.state_dir),
                "BELBERRY_BITRIX24_APP_INSTALL_STATE_FILE": str(self.state_path),
                "BELBERRY_BITRIX24_CLIENT_ID": "cid",
                "BELBERRY_BITRIX24_CLIENT_SECRET": "secret",
                "BELBERRY_BITRIX24_TIMEOUT_SEC": "7",
                "BITRIX_APP_STATE_DIR": "/opt/openclaw/state/bitrix_app",
            },
            transport=transport,
        )

        self.assertEqual(auth.state_dir, self.state_dir)
        self.assertEqual(auth.client_id, "cid")
        self.assertEqual(auth.client_secret, "secret")
        self.assertEqual(auth.timeout_sec, 7)

    def test_from_env_requires_belberry_state_dir_without_legacy_default(self) -> None:
        with self.assertRaisesRegex(BitrixOAuthError, "BELBERRY_BITRIX24_APP_STATE_DIR"):
            BitrixOAuth.from_env({"BITRIX_APP_STATE_DIR": "/opt/openclaw/state/bitrix_app"}, transport=FakeTransport([]))

    def test_load_state_picks_latest_valid_state(self) -> None:
        self.write_state(name="install.latest.json", saved_at="2026-05-10T08:00:00+03:00")
        self.write_state(name="handler.latest.json", saved_at="2026-05-10T09:00:00+03:00", **{"auth[member_id]": "latest"})

        state = self.make_auth().load_state()

        self.assertEqual(state.member_id, "latest")
        self.assertEqual(state.path.name, "handler.latest.json")

    def test_load_state_uses_explicit_state_file(self) -> None:
        explicit = self.write_state(name="custom.json")

        state = self.make_auth(state_file=explicit).load_state()

        self.assertEqual(state.path, explicit)

    def test_load_state_rejects_missing_or_invalid_state(self) -> None:
        (self.state_dir / "install.latest.json").write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(BitrixOAuthError, "не найден"):
            self.make_auth().load_state()

    def test_summary_masks_tokens(self) -> None:
        self.write_state()

        summary = self.make_auth().summary()

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["access_token"], "acce***3456")
        self.assertEqual(summary["refresh_token"], "refr***3456")

    def test_summary_reports_not_configured_without_secret(self) -> None:
        summary = self.make_auth().summary()

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["status"], "not configured")

    def test_is_configured(self) -> None:
        self.assertFalse(self.make_auth().is_configured())
        self.write_state()
        self.assertTrue(self.make_auth().is_configured())

    def test_call_payload_posts_to_client_endpoint_with_flattened_params(self) -> None:
        self.write_state()
        transport = FakeTransport([BitrixHttpResponse(200, json.dumps({"result": {"ok": True}}))])

        payload = self.make_auth(transport=transport).call_payload(
            "crm.deal.get",
            params={"id": 10, "filter": {"A": "B"}, "ids": [1, 2]},
        )

        self.assertEqual(payload["result"], {"ok": True})
        request = transport.requests[0]
        self.assertEqual(request.url, "https://portal.example/rest/crm.deal.get.json")
        body = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(body["auth"], ["access-token-123456"])
        self.assertEqual(body["id"], ["10"])
        self.assertEqual(body["filter[A]"], ["B"])
        self.assertEqual(body["ids[]"], ["1", "2"])

    def test_call_method_returns_default_for_missing_result(self) -> None:
        self.write_state()
        transport = FakeTransport([BitrixHttpResponse(200, "{}")])

        result = self.make_auth(transport=transport).call_method("crm.deal.get", default=[])

        self.assertEqual(result, [])

    def test_call_payload_refreshes_on_expired_token_and_retries_method(self) -> None:
        self.write_state()
        transport = FakeTransport(
            [
                BitrixHttpResponse(200, json.dumps({"error": "EXPIRED_TOKEN", "error_description": "expired"})),
                BitrixHttpResponse(
                    200,
                    json.dumps(
                        {
                            "access_token": "new-access-token",
                            "refresh_token": "new-refresh-token",
                            "client_endpoint": "https://portal.example/rest",
                            "server_endpoint": "https://portal.example",
                            "domain": "portal.example",
                            "member_id": "member-2",
                            "status": "L",
                        }
                    ),
                ),
                BitrixHttpResponse(200, json.dumps({"result": {"ID": "10"}})),
            ]
        )

        payload = self.make_auth(transport=transport).call_payload("crm.deal.get", params={"id": 10})

        self.assertEqual(payload["result"]["ID"], "10")
        self.assertEqual(transport.requests[1].url, "https://portal.example/oauth/token/")
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["payload"]["auth[access_token]"], "new-access-token")
        self.assertEqual(saved["payload"]["auth[refresh_token]"], "new-refresh-token")
        self.assertEqual(oct(self.state_path.stat().st_mode & 0o777), "0o600")

    def test_refresh_uses_only_server_endpoint_not_config_or_public_fallbacks(self) -> None:
        self.write_state(**{"auth[server_endpoint]": "https://server.example/install"})
        transport = FakeTransport(
            [
                BitrixHttpResponse(
                    200,
                    json.dumps(
                        {
                            "access_token": "new-access-token",
                            "refresh_token": "new-refresh-token",
                            "client_endpoint": "https://portal.example/rest",
                        }
                    ),
                )
            ]
        )

        self.make_auth(transport=transport).refresh_access_token()

        self.assertEqual([req.url for req in transport.requests], ["https://server.example/oauth/token/"])
        self.assertNotIn("oauth.bitrix.info", transport.requests[0].url)
        self.assertNotIn("oauth.bitrix24.tech", transport.requests[0].url)

    def test_refresh_requires_client_credentials_refresh_token_and_server_endpoint(self) -> None:
        self.write_state(**{"auth[refresh_token]": ""})
        with self.assertRaisesRegex(BitrixOAuthError, "refresh token"):
            self.make_auth().refresh_access_token()

        self.write_state(**{"auth[server_endpoint]": ""})
        with self.assertRaisesRegex(BitrixOAuthError, "server_endpoint"):
            self.make_auth().refresh_access_token()

        self.write_state()
        with self.assertRaisesRegex(BitrixOAuthError, "client_id"):
            BitrixOAuth(state_dir=self.state_dir, transport=FakeTransport([])).refresh_access_token()

    def test_refresh_rejects_invalid_server_endpoint_and_payload(self) -> None:
        self.write_state(**{"auth[server_endpoint]": "not-url"})
        with self.assertRaisesRegex(BitrixOAuthError, "server_endpoint"):
            self.make_auth().refresh_access_token()

        self.write_state()
        transport = FakeTransport([BitrixHttpResponse(200, json.dumps({"access_token": "new"}))])
        with self.assertRaisesRegex(BitrixOAuthError, "неполный payload"):
            self.make_auth(transport=transport).refresh_access_token()

    def test_request_json_retries_rate_limit_with_fake_sleep(self) -> None:
        self.write_state()
        sleeps: list[float] = []
        transport = FakeTransport(
            [
                BitrixHttpResponse(429, json.dumps({"error": "QUERY_LIMIT_EXCEEDED", "error_description": "slow"})),
                BitrixHttpResponse(200, json.dumps({"result": {"ok": True}})),
            ]
        )

        payload = self.make_auth(transport=transport, sleep=sleeps.append).call_payload("crm.deal.get")

        self.assertEqual(payload["result"], {"ok": True})
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(len(transport.requests), 2)

    def test_request_json_sanitizes_url_errors_and_invalid_payloads(self) -> None:
        self.write_state()
        transport = FakeTransport(exc=RuntimeError("failed https://portal.example/rest/secret"))
        with self.assertRaisesRegex(BitrixOAuthError, r"https://portal.example/\\*\\*\\*"):
            self.make_auth(transport=transport).call_payload("crm.deal.get")

        invalid_json = FakeTransport([BitrixHttpResponse(200, "{broken")])
        with self.assertRaisesRegex(BitrixOAuthError, "невалидный JSON"):
            self.make_auth(transport=invalid_json).call_payload("crm.deal.get")

        invalid_payload = FakeTransport([BitrixHttpResponse(200, "[]")])
        with self.assertRaisesRegex(BitrixOAuthError, "неожиданный формат"):
            self.make_auth(transport=invalid_payload).call_payload("crm.deal.get")

    def test_error_payload_category_and_to_payload(self) -> None:
        self.write_state()
        transport = FakeTransport(
            [BitrixHttpResponse(403, json.dumps({"error": "ERROR_METHOD_NOT_FOUND", "error_description": "no"}))]
        )

        with self.assertRaises(BitrixOAuthError) as ctx:
            self.make_auth(transport=transport).call_payload("crm.unknown")

        self.assertEqual(ctx.exception.to_status(), "method not found")
        payload = ctx.exception.to_payload()
        self.assertEqual(payload["status"], "method not found")
        self.assertEqual(payload["http_status"], 403)

    def test_access_denied_and_generic_error_statuses(self) -> None:
        access_denied = BitrixOAuthError("denied", category="access_denied")
        generic = BitrixOAuthError("failed")

        self.assertEqual(access_denied.to_status(), "access denied")
        self.assertEqual(generic.to_status(), "error")

    def test_call_payload_does_not_refresh_non_expired_errors(self) -> None:
        self.write_state()
        transport = FakeTransport([BitrixHttpResponse(403, json.dumps({"error": "ACCESS_DENIED"}))])

        with self.assertRaisesRegex(BitrixOAuthError, "ACCESS_DENIED"):
            self.make_auth(transport=transport).call_payload("crm.deal.get")

        self.assertEqual(len(transport.requests), 1)

    def test_request_json_handles_invalid_error_json_and_transport_bitrix_error(self) -> None:
        self.write_state()
        invalid_error_json = FakeTransport([BitrixHttpResponse(500, "not json")])
        with self.assertRaisesRegex(BitrixOAuthError, "Bitrix request failed"):
            self.make_auth(transport=invalid_error_json).call_payload("crm.deal.get")

        sleeps: list[float] = []
        rate_limited_once = FakeTransport(
            [
                BitrixHttpResponse(200, json.dumps({"result": {"ok": True}})),
            ],
            exc=BitrixOAuthError("too many requests", code="TOO_MANY_REQUESTS", http_status=429),
        )

        def transport(request: BitrixHttpRequest, timeout: int) -> BitrixHttpResponse:
            if not rate_limited_once.requests:
                rate_limited_once.requests.append(request)
                raise BitrixOAuthError("too many requests", code="TOO_MANY_REQUESTS", http_status=429)
            return BitrixHttpResponse(200, json.dumps({"result": {"ok": True}}))

        payload = self.make_auth(transport=transport, sleep=sleeps.append).call_payload("crm.deal.get")
        self.assertEqual(payload["result"], {"ok": True})
        self.assertEqual(sleeps, [1.0])

    def test_call_payload_default_is_returned_for_empty_payload(self) -> None:
        self.write_state()
        transport = FakeTransport([BitrixHttpResponse(200, "")])

        payload = self.make_auth(transport=transport).call_payload("crm.deal.get", default={"fallback": True})

        self.assertEqual(payload, {"fallback": True})

    def test_call_with_invalid_loaded_state_is_rejected(self) -> None:
        state = BitrixAppState(
            self.state_path,
            {"payload": {"auth[client_endpoint]": "https://portal.example/rest"}},
        )

        with self.assertRaisesRegex(BitrixOAuthError, "access token"):
            self.make_auth()._call_payload_with_state(state, "crm.deal.get")

    def test_list_method_handles_pagination_and_limits(self) -> None:
        self.write_state()
        transport = FakeTransport(
            [
                BitrixHttpResponse(200, json.dumps({"result": [{"ID": "1"}], "next": 2})),
                BitrixHttpResponse(200, json.dumps({"result": {"items": [{"ID": "2"}, {"ID": "3"}]}})),
            ]
        )

        items = self.make_auth(transport=transport).list_method("crm.deal.list", limit=2)

        self.assertEqual(items, [{"ID": "1"}, {"ID": "2"}])

    def test_list_method_stops_on_invalid_next_or_empty_chunk(self) -> None:
        self.write_state()
        invalid_next = FakeTransport([BitrixHttpResponse(200, json.dumps({"result": [{"ID": "1"}], "next": "bad"}))])
        self.assertEqual(self.make_auth(transport=invalid_next).list_method("m"), [{"ID": "1"}])

        empty_chunk = FakeTransport([BitrixHttpResponse(200, json.dumps({"result": [], "next": 2}))])
        self.assertEqual(self.make_auth(transport=empty_chunk).list_method("m"), [])

        same_next = FakeTransport([BitrixHttpResponse(200, json.dumps({"result": [{"ID": "1"}], "next": 0}))])
        self.assertEqual(self.make_auth(transport=same_next).list_method("m"), [{"ID": "1"}])

        no_list_result = FakeTransport([BitrixHttpResponse(200, json.dumps({"result": {"other": []}}))])
        self.assertEqual(self.make_auth(transport=no_list_result).list_method("m"), [])

    def test_helpers_handle_empty_invalid_and_partial_values(self) -> None:
        self.assertEqual(oauth._parse_saved_at("").year, 1970)
        self.assertEqual(oauth._parse_saved_at("not-date").year, 1970)
        self.assertEqual(oauth._flatten_params("empty", None), [])
        self.assertEqual(oauth._extract_result_list("not-list"), [])

    def test_load_record_skips_invalid_json_and_payload_without_auth(self) -> None:
        bad_json = self.state_dir / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        self.assertIsNone(self.make_auth()._load_record(bad_json))

        no_auth = self.state_dir / "no-auth.json"
        no_auth.write_text(json.dumps({"payload": {"auth[client_endpoint]": "https://portal.example/rest"}}), encoding="utf-8")
        self.assertIsNone(self.make_auth()._load_record(no_auth))

    def test_sanitize_bitrix_text_masks_urls(self) -> None:
        text = sanitize_bitrix_text(
            "failed https://portal.example/rest/123/secret/crm.deal.get",
            endpoint="https://portal.example/rest",
        )

        self.assertEqual(text, "failed https://portal.example/***")

    def test_urllib_transport_success_http_error_and_url_error_are_patchable(self) -> None:
        with patch("belberry.bitrix24.providers.bitrix_oauth.urlopen", return_value=FakeResponse('{"ok": true}')):
            response = oauth.urllib_transport(BitrixHttpRequest("https://x", "POST", b"", {}), 3)
        self.assertEqual(response.body, '{"ok": true}')
        self.assertEqual(response.status, 200)

        http_error = HTTPError("https://x", 500, "bad", {}, BytesIO(b'{"error":"bad"}'))
        with patch("belberry.bitrix24.providers.bitrix_oauth.urlopen", side_effect=http_error):
            response = oauth.urllib_transport(BitrixHttpRequest("https://x", "POST", b"", {}), 3)
        self.assertEqual(response.status, 500)

        with patch("belberry.bitrix24.providers.bitrix_oauth.urlopen", side_effect=URLError("down")):
            with self.assertRaisesRegex(BitrixOAuthError, "down"):
                oauth.urllib_transport(BitrixHttpRequest("https://x", "POST", b"", {}), 3)


if __name__ == "__main__":
    unittest.main()
