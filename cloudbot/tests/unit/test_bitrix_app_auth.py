from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAPIError, BitrixAppAuth


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _http_error(url: str, status: int, payload: dict[str, object]) -> HTTPError:
    return HTTPError(
        url=url,
        code=status,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
    )


def _state_record(saved_at: str, *, access_token: str, refresh_token: str, client_endpoint: str) -> dict[str, object]:
    return {
        "saved_at": saved_at,
        "event": "install",
        "payload": {
            "auth[domain]": "belberrycrm.bitrix24.ru",
            "auth[member_id]": "member-1",
            "auth[status]": "L",
            "auth[access_token]": access_token,
            "auth[refresh_token]": refresh_token,
            "auth[client_endpoint]": client_endpoint,
            "auth[server_endpoint]": "https://oauth.bitrix24.tech/rest/",
        },
        "summary": {
            "domain": "belberrycrm.bitrix24.ru",
            "member_id": "member-1",
            "status": "L",
            "auth_present": True,
            "refresh_present": True,
        },
    }


class BitrixAppAuthTests(unittest.TestCase):
    def test_prefers_newest_handler_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="install-token",
                        refresh_token="install-refresh",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (state_dir / "handler.latest.json").write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:05:00+03:00",
                        access_token="handler-token",
                        refresh_token="handler-refresh",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            state = auth.load_state()
            self.assertEqual(state.path.name, "handler.latest.json")
            self.assertEqual(state.access_token, "handler-token")

    def test_call_method_uses_saved_access_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            state_path = state_dir / "install.latest.json"
            state_path.write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="live-token",
                        refresh_token="live-refresh",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            requests: list[object] = []

            def fake_urlopen(request, timeout=20):  # noqa: ANN001
                requests.append(request)
                return _FakeResponse({"result": [{"ID": "1"}]})

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            with patch("cloudbot.providers.bitrix.bitrix_app_auth.urlopen", side_effect=fake_urlopen):
                payload = auth.call_method("imopenlines.config.list.get")

            self.assertEqual(payload, [{"ID": "1"}])
            self.assertEqual(len(requests), 1)
            body = requests[0].data.decode("utf-8")
            self.assertIn("auth=live-token", body)

    def test_list_method_paginates_with_next_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="live-token",
                        refresh_token="live-refresh",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            seen_bodies: list[str] = []

            def fake_urlopen(request, timeout=20):  # noqa: ANN001
                body = request.data.decode("utf-8")
                seen_bodies.append(body)
                if "start=0" in body:
                    return _FakeResponse({"result": [{"ID": "1"}, {"ID": "2"}], "next": 2})
                if "start=2" in body:
                    return _FakeResponse({"result": [{"ID": "3"}]})
                raise AssertionError(body)

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            with patch("cloudbot.providers.bitrix.bitrix_app_auth.urlopen", side_effect=fake_urlopen):
                payload = auth.list_method("crm.deal.list", params={"select": ["ID"]}, limit=10)

            self.assertEqual([item["ID"] for item in payload], ["1", "2", "3"])
            self.assertEqual(len(seen_bodies), 2)

    def test_call_method_retries_on_rate_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="live-token",
                        refresh_token="live-refresh",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            attempts = {"count": 0}
            sleep_calls: list[float] = []

            def fake_urlopen(request, timeout=20):  # noqa: ANN001
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise _http_error(
                        request.full_url,
                        429,
                        {"error": "QUERY_LIMIT_EXCEEDED", "error_description": "Too many requests"},
                    )
                return _FakeResponse({"result": [{"ID": "1"}]})

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            with (
                patch("cloudbot.providers.bitrix.bitrix_app_auth.urlopen", side_effect=fake_urlopen),
                patch("cloudbot.providers.bitrix.bitrix_app_auth.time.sleep", side_effect=lambda value: sleep_calls.append(value)),
            ):
                payload = auth.call_method("crm.timeline.comment.list")

            self.assertEqual(payload, [{"ID": "1"}])
            self.assertEqual(attempts["count"], 3)
            self.assertEqual(sleep_calls, [1.0, 2.0])

    def test_expired_token_triggers_refresh_and_persists_new_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            state_path = state_dir / "install.latest.json"
            state_path.write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="expired-token",
                        refresh_token="refresh-token-1",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            calls: list[str] = []

            def fake_urlopen(request, timeout=20):  # noqa: ANN001
                calls.append(str(request.full_url))
                if request.full_url.endswith("/imopenlines.session.history.get.json"):
                    body = request.data.decode("utf-8")
                    if "auth=expired-token" in body:
                        raise _http_error(
                            request.full_url,
                            401,
                            {"error": "expired_token", "error_description": "The access token provided has expired"},
                        )
                    if "auth=fresh-token" in body:
                        return _FakeResponse({"result": [{"OPERATOR_ID": "2806"}]})
                if request.full_url.endswith("/oauth/token/"):
                    return _FakeResponse(
                        {
                            "access_token": "fresh-token",
                            "refresh_token": "refresh-token-2",
                            "client_endpoint": "https://portal/rest",
                            "server_endpoint": "https://oauth.bitrix24.tech/rest/",
                            "domain": "belberrycrm.bitrix24.ru",
                            "status": "L",
                        }
                    )
                raise AssertionError(f"Unexpected url: {request.full_url}")

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            with patch("cloudbot.providers.bitrix.bitrix_app_auth.urlopen", side_effect=fake_urlopen):
                payload = auth.call_method("imopenlines.session.history.get", params={"FILTER": {"ID": "1"}})

            self.assertEqual(payload, [{"OPERATOR_ID": "2806"}])
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["payload"]["auth[access_token]"], "fresh-token")
            self.assertEqual(saved["payload"]["auth[refresh_token]"], "refresh-token-2")
            self.assertIn("auth_refreshed_at", saved)
            self.assertGreaterEqual(len(calls), 3)

    def test_refresh_invalid_client_raises_bitrix_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            (state_dir / "install.latest.json").write_text(
                json.dumps(
                    _state_record(
                        "2026-03-12T15:00:00+03:00",
                        access_token="expired-token",
                        refresh_token="refresh-token-1",
                        client_endpoint="https://portal/rest",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_urlopen(request, timeout=20):  # noqa: ANN001
                if request.full_url.endswith("/imopenlines.session.history.get.json"):
                    raise _http_error(
                        request.full_url,
                        401,
                        {"error": "expired_token", "error_description": "The access token provided has expired"},
                    )
                if request.full_url.endswith("/oauth/token/"):
                    raise _http_error(
                        request.full_url,
                        401,
                        {"error": "invalid_client", "error_description": "Invalid client id"},
                    )
                raise AssertionError(f"Unexpected url: {request.full_url}")

            auth = BitrixAppAuth(
                state_dir=state_dir,
                client_id="local.app",
                client_secret="secret",
            )

            with patch("cloudbot.providers.bitrix.bitrix_app_auth.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(BitrixAPIError) as raised:
                    auth.call_method("imopenlines.session.history.get", params={"FILTER": {"ID": "1"}})

            self.assertIn("Bitrix OAuth refresh не удался", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
