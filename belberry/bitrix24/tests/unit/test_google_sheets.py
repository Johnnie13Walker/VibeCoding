from __future__ import annotations

import base64
import json
import tempfile
import unittest
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from belberry.bitrix24.providers.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsError,
    Response,
    SheetSnapshot,
    _b64url,
    _build_jwt_assertion,
    _column_name,
    _json_b64url,
    _load_json_object,
    _parse_json_response,
    _sheet_names,
    _sign_rs256,
    _string_rows,
    sheets_methods_used,
    RW_SCOPE,
    urllib_transport,
)


def _decode_jwt_segment(segment: str) -> dict[str, Any]:
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode((segment + padding).encode("ascii")))


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []
        self.token_calls = 0
        self.fail_values_once = False
        self.metadata_payload: dict[str, Any] = {
            "sheets": [{"properties": {"title": "Дубли Реанимация"}}],
        }
        self.values_payload: dict[str, Any] = {
            "values": [
                ["Domain", "IDs", "Target"],
                ["example.ru", "10,20", "10"],
                ["empty.ru"],
            ]
        }
        self.write_payload: dict[str, Any] = {"ok": True}

    def __call__(self, request, timeout_sec: int) -> Response:
        headers = {str(key): str(value) for key, value in request.header_items()}
        self.calls.append((request.get_method(), request.full_url, request.data, headers))
        if request.full_url == "https://oauth2.googleapis.com/token":
            self.token_calls += 1
            body = parse_qs((request.data or b"").decode("utf-8"))
            assertion = body["assertion"][0]
            header, claims, signature = assertion.split(".")
            self.last_jwt_header = _decode_jwt_segment(header)
            self.last_jwt_claims = _decode_jwt_segment(claims)
            self.last_jwt_signature = signature
            return Response(status=200, body=json.dumps({"access_token": "access-token", "expires_in": 3600}))
        if request.full_url.startswith("https://sheets.googleapis.com/v4/spreadsheets/sheet-123/values/"):
            if request.get_method() in {"PUT", "POST"}:
                return Response(status=200, body=json.dumps(self.write_payload))
            if self.fail_values_once:
                self.fail_values_once = False
                return Response(status=503, body=json.dumps({"error": {"message": "try later"}}))
            return Response(status=200, body=json.dumps(self.values_payload))
        if request.full_url == "https://sheets.googleapis.com/v4/spreadsheets/sheet-123":
            return Response(status=200, body=json.dumps(self.metadata_payload))
        if request.full_url == "https://sheets.googleapis.com/v4/spreadsheets/sheet-123:batchUpdate":
            return Response(status=200, body=json.dumps({"replies": [{"addSheet": {"properties": {"title": "Дубликаты 3"}}}]}))
        return Response(status=404, body=json.dumps({"error": {"message": "not found"}}))


class GoogleSheetsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.private_key = _private_key_pem()
        self.service_account_path = Path(self.tmp.name) / "sa.json"
        self.service_account_path.write_text(
            json.dumps(
                {
                    "client_email": "service@example.iam.gserviceaccount.com",
                    "private_key": self.private_key,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            ),
            encoding="utf-8",
        )
        self.now = datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc)
        self.transport = FakeTransport()
        self.sleeps: list[float] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def client(self) -> GoogleSheetsClient:
        return GoogleSheetsClient(
            service_account_path=self.service_account_path,
            transport=self.transport,
            sleep=self.sleeps.append,
            now_utc=lambda: self.now,
        )

    def test_sheets_methods_used_declares_reads_and_writes(self) -> None:
        methods = sheets_methods_used()

        self.assertEqual(
            methods,
            (
                "spreadsheets.values.get",
                "spreadsheets.get",
                "spreadsheets.batchUpdate",
                "spreadsheets.values.update",
                "spreadsheets.values.append",
            ),
        )

    def test_from_env_reads_service_account_path(self) -> None:
        client = GoogleSheetsClient.from_env(
            {"BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON": str(self.service_account_path)},
            transport=self.transport,
            sleep=self.sleeps.append,
            now_utc=lambda: self.now,
        )

        self.assertEqual(client.service_account_path, self.service_account_path)

    def test_from_env_rejects_missing_path(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "GOOGLE_SERVICE_ACCOUNT_JSON"):
            GoogleSheetsClient.from_env({}, transport=self.transport)

    def test_metadata_uses_bearer_token_and_get(self) -> None:
        payload = self.client().metadata("sheet-123")

        self.assertEqual(payload, self.transport.metadata_payload)
        methods = [call[0] for call in self.transport.calls]
        self.assertEqual(methods, ["POST", "GET"])
        self.assertIn(("aud", "https://oauth2.googleapis.com/token"), self.transport.last_jwt_claims.items())
        self.assertEqual(self.transport.last_jwt_claims["iat"], 1778405400)
        self.assertTrue(self.transport.calls[1][3]["Authorization"].startswith("Bearer access-token"))

    def test_read_snapshot_returns_header_rows_and_msk_time(self) -> None:
        snapshot = self.client().read_snapshot("sheet-123", "Дубли Реанимация")

        self.assertIsInstance(snapshot, SheetSnapshot)
        self.assertEqual(snapshot.sheet_id, "sheet-123")
        self.assertEqual(snapshot.sheet_name, "Дубли Реанимация")
        self.assertEqual(snapshot.header, ("Domain", "IDs", "Target"))
        self.assertEqual(snapshot.rows, (("example.ru", "10,20", "10"), ("empty.ru",)))
        self.assertEqual(snapshot.fetched_at_msk, "2026-05-10T12:30:00+03:00")
        values_url = self.transport.calls[-1][1]
        self.assertIn("values/", values_url)
        self.assertIn("Дубли Реанимация!A:Z", unquote(values_url))

    def test_access_token_is_cached_until_expiry(self) -> None:
        client = self.client()

        client.metadata("sheet-123")
        client.metadata("sheet-123")

        self.assertEqual(self.transport.token_calls, 1)
        self.assertEqual([call[0] for call in self.transport.calls], ["POST", "GET", "GET"])

    def test_retry_uses_injected_sleep(self) -> None:
        self.transport.fail_values_once = True

        snapshot = self.client().read_snapshot("sheet-123", "Дубли Реанимация")

        self.assertEqual(snapshot.header, ("Domain", "IDs", "Target"))
        self.assertEqual(self.sleeps, [1.0])

    def test_sheet_not_found_raises(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "sheet not found"):
            self.client().read_snapshot("sheet-123", "Missing")

    def test_required_ids_are_validated(self) -> None:
        client = self.client()

        with self.assertRaisesRegex(GoogleSheetsError, "sheet_id"):
            client.metadata("")
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_id"):
            client.read_snapshot("", "Дубли Реанимация")
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_name"):
            client.read_snapshot("sheet-123", "")

    def test_google_error_payload_raises(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "not found"):
            self.client().metadata("unknown")

    def test_invalid_json_response_raises(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "invalid JSON"):
            _parse_json_response(Response(status=200, body="{bad"), context="ctx")

    def test_unexpected_json_response_raises(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "unexpected payload"):
            _parse_json_response(Response(status=200, body="[]"), context="ctx")

    def test_token_response_requires_access_token(self) -> None:
        class NoToken(FakeTransport):
            def __call__(self, request, timeout_sec):
                if request.full_url == "https://oauth2.googleapis.com/token":
                    return Response(status=200, body=json.dumps({"expires_in": 3600}))
                return super().__call__(request, timeout_sec)

        client = GoogleSheetsClient(
            service_account_path=self.service_account_path,
            transport=NoToken(),
            now_utc=lambda: self.now,
        )

        with self.assertRaisesRegex(GoogleSheetsError, "access_token"):
            client.metadata("sheet-123")

    def test_token_response_accepts_bad_expires_in(self) -> None:
        class BadExpires(FakeTransport):
            def __call__(self, request, timeout_sec):
                if request.full_url == "https://oauth2.googleapis.com/token":
                    self.calls.append((request.get_method(), request.full_url, request.data, {}))
                    return Response(status=200, body=json.dumps({"access_token": "token", "expires_in": "bad"}))
                return super().__call__(request, timeout_sec)

        client = GoogleSheetsClient(
            service_account_path=self.service_account_path,
            transport=BadExpires(),
            now_utc=lambda: self.now,
        )

        self.assertIn("sheets", client.metadata("sheet-123"))

    def test_service_account_file_validation(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "not found"):
            GoogleSheetsClient(service_account_path=Path(self.tmp.name) / "missing.json").metadata("sheet-123")
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{bad", encoding="utf-8")
        with self.assertRaisesRegex(GoogleSheetsError, "invalid"):
            GoogleSheetsClient(service_account_path=bad).metadata("sheet-123")
        array = Path(self.tmp.name) / "array.json"
        array.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(GoogleSheetsError, "object"):
            _load_json_object(array)
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            with self.assertRaisesRegex(GoogleSheetsError, "cannot be read"):
                _load_json_object(self.service_account_path)

    def test_service_account_requires_fields_and_valid_key(self) -> None:
        missing = Path(self.tmp.name) / "missing-field.json"
        missing.write_text(json.dumps({"client_email": "service@example"}), encoding="utf-8")
        with self.assertRaisesRegex(GoogleSheetsError, "private_key"):
            GoogleSheetsClient(service_account_path=missing, transport=self.transport).metadata("sheet-123")

        invalid = Path(self.tmp.name) / "invalid-key.json"
        invalid.write_text(
            json.dumps({"client_email": "service@example", "private_key": "bad"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GoogleSheetsError, "private_key"):
            GoogleSheetsClient(service_account_path=invalid, transport=self.transport).metadata("sheet-123")

    def test_jwt_helpers_are_deterministic(self) -> None:
        self.assertEqual(_b64url(b"\xfb\xff"), "-_8")
        self.assertEqual(_decode_jwt_segment(_json_b64url({"b": 2, "a": 1})), {"a": 1, "b": 2})

        jwt = _build_jwt_assertion(
            client_email="service@example",
            private_key=self.private_key,
            token_uri="https://oauth2.googleapis.com/token",
            now=self.now,
        )

        header, claims, signature = jwt.split(".")
        self.assertEqual(_decode_jwt_segment(header), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(_decode_jwt_segment(claims)["exp"], 1778408700)
        self.assertEqual(_decode_jwt_segment(claims)["scope"], "https://www.googleapis.com/auth/spreadsheets.readonly")
        self.assertTrue(signature)

    def test_write_methods_use_correct_scope(self) -> None:
        client = self.client()

        client.write_header("sheet-123", "Дубликаты 3", ["A"])

        self.assertEqual(self.transport.last_jwt_claims["scope"], RW_SCOPE)

    def test_add_sheet_uses_batch_update_body_and_rejects_existing(self) -> None:
        client = self.client()

        payload = client.add_sheet("sheet-123", "Дубликаты 3")

        self.assertIn("replies", payload)
        self.assertEqual([call[0] for call in self.transport.calls], ["POST", "GET", "POST", "POST"])
        body = json.loads((self.transport.calls[-1][2] or b"").decode("utf-8"))
        self.assertEqual(body["requests"][0]["addSheet"]["properties"]["title"], "Дубликаты 3")

        self.transport.metadata_payload = {"sheets": [{"properties": {"title": "Дубликаты 3"}}]}
        with self.assertRaisesRegex(GoogleSheetsError, "already exists"):
            client.add_sheet("sheet-123", "Дубликаты 3")

    def test_write_header_uses_values_update_range(self) -> None:
        client = self.client()

        client.write_header("sheet-123", "Дубликаты 3", ["A", "B", "C"])

        method, url, data, _headers = self.transport.calls[-1]
        self.assertEqual(method, "PUT")
        self.assertIn("valueInputOption=RAW", url)
        self.assertIn("Дубликаты 3!A1:C1", unquote(url))
        self.assertEqual(json.loads((data or b"").decode("utf-8")), {"values": [["A", "B", "C"]]})

    def test_append_rows_uses_values_append_range_and_empty_rows_noop(self) -> None:
        client = self.client()

        self.assertEqual(client.append_rows("sheet-123", "Дубликаты 3", []), {"updates": {"updatedRows": 0}})
        client.append_rows("sheet-123", "Дубликаты 3", [["1", "Title"]])

        method, url, data, _headers = self.transport.calls[-1]
        self.assertEqual(method, "POST")
        self.assertIn("insertDataOption=INSERT_ROWS", url)
        self.assertIn("valueInputOption=RAW", url)
        self.assertIn("Дубликаты 3!A2:append", unquote(url))
        self.assertEqual(json.loads((data or b"").decode("utf-8")), {"values": [["1", "Title"]]})

    def test_write_methods_validate_required_inputs(self) -> None:
        client = self.client()

        with self.assertRaisesRegex(GoogleSheetsError, "sheet_id"):
            client.add_sheet("", "x")
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_name"):
            client.add_sheet("sheet-123", "")
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_id"):
            client.write_header("", "x", ["A"])
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_name"):
            client.write_header("sheet-123", "", ["A"])
        with self.assertRaisesRegex(GoogleSheetsError, "header"):
            client.write_header("sheet-123", "x", [])
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_id"):
            client.append_rows("", "x", [["x"]])
        with self.assertRaisesRegex(GoogleSheetsError, "sheet_name"):
            client.append_rows("sheet-123", "", [["x"]])

    def test_sheet_names_and_column_name_edge_cases(self) -> None:
        self.assertEqual(_sheet_names({}), set())
        self.assertEqual(_column_name(27), "AA")
        with self.assertRaisesRegex(GoogleSheetsError, "column index"):
            _column_name(0)

    def test_jwt_helper_accepts_naive_now(self) -> None:
        jwt = _build_jwt_assertion(
            client_email="service@example",
            private_key=self.private_key,
            token_uri="https://oauth2.googleapis.com/token",
            now=datetime(2026, 5, 10, 9, 30),
        )

        claims = _decode_jwt_segment(jwt.split(".")[1])
        self.assertEqual(claims["iat"], 1778405400)

    def test_signer_rejects_invalid_private_key(self) -> None:
        with self.assertRaisesRegex(GoogleSheetsError, "private_key"):
            _sign_rs256("bad", b"payload")

    def test_signer_reports_missing_crypto(self) -> None:
        original_import = __import__

        def blocked_import(name, *args, **kwargs):
            if str(name).startswith("cryptography"):
                raise ImportError("blocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=blocked_import):
            with self.assertRaisesRegex(GoogleSheetsError, "RS256"):
                _sign_rs256(self.private_key, b"payload")

    def test_naive_now_is_treated_as_utc(self) -> None:
        client = GoogleSheetsClient(
            service_account_path=self.service_account_path,
            transport=self.transport,
            now_utc=lambda: datetime(2026, 5, 10, 9, 30),
        )

        snapshot = client.read_snapshot("sheet-123", "Дубли Реанимация")

        self.assertEqual(snapshot.fetched_at_msk, "2026-05-10T12:30:00+03:00")

    def test_empty_values_payload_returns_empty_snapshot(self) -> None:
        self.transport.values_payload = {}

        snapshot = self.client().read_snapshot("sheet-123", "Дубли Реанимация")

        self.assertEqual(snapshot.header, ())
        self.assertEqual(snapshot.rows, ())

    def test_string_rows_ignores_non_list_rows_and_non_list_values(self) -> None:
        self.assertEqual(_string_rows({"bad": "shape"}), ())
        self.assertEqual(_string_rows([["a"], "bad", [1, None]]), (("a",), ("1", "None")))

    def test_urllib_transport_success_http_error_and_url_error(self) -> None:
        class OkResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"ok": true}'

        request = Request("https://example.test")
        with patch("belberry.bitrix24.providers.google_sheets.urlopen", return_value=OkResponse()):
            self.assertEqual(urllib_transport(request, 3), Response(status=200, body='{"ok": true}'))

        http_error = HTTPError(
            url="https://example.test",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=BytesIO(b'{"error": "denied"}'),
        )
        with patch("belberry.bitrix24.providers.google_sheets.urlopen", side_effect=http_error):
            self.assertEqual(urllib_transport(request, 3), Response(status=403, body='{"error": "denied"}'))

        with patch("belberry.bitrix24.providers.google_sheets.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(GoogleSheetsError, "offline"):
                urllib_transport(request, 3)


if __name__ == "__main__":
    unittest.main()
