from __future__ import annotations

import io
import json
import runpy
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import warnings
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from belberry.bitrix24.scripts import oauth_install

MSK = ZoneInfo("Europe/Moscow")


def sample_payload(**overrides):
    payload = {
        "AUTH_ID": "access-secret-token",
        "REFRESH_ID": "refresh-secret-token",
        "client_endpoint": "https://portal.example/rest",
        "server_endpoint": "https://oauth.example/rest",
        "DOMAIN": "portal.example",
        "member_id": "member-1",
        "status": "L",
    }
    payload.update(overrides)
    return payload


def form_body(payload: dict[str, str]) -> bytes:
    return urllib.parse.urlencode(payload).encode("utf-8")


def read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class OAuthInstallTests(unittest.TestCase):
    def fixed_now(self) -> datetime:
        return datetime(2026, 5, 10, 14, 30, 0, tzinfo=MSK)

    def test_form_body_parses_bitrix_fields(self) -> None:
        payload = oauth_install.InstallPayload.from_form_body(
            b"AUTH_ID=access-token&REFRESH_ID=refresh-token&client_endpoint=https%3A%2F%2Fportal.example%2Frest"
        )

        self.assertEqual(payload.raw["AUTH_ID"], "access-token")
        self.assertEqual(payload.raw["REFRESH_ID"], "refresh-token")
        self.assertTrue(payload.is_valid())

    def test_json_accepts_wrapped_payload(self) -> None:
        payload = oauth_install.InstallPayload.from_json({"payload": sample_payload()})

        self.assertEqual(payload.raw["AUTH_ID"], "access-secret-token")
        self.assertTrue(payload.is_valid())

    def test_json_accepts_flat_payload(self) -> None:
        payload = oauth_install.InstallPayload.from_json(sample_payload())

        self.assertEqual(payload.raw["DOMAIN"], "portal.example")

    def test_state_record_uses_oauth_shape(self) -> None:
        record = oauth_install.InstallPayload.from_json(sample_payload()).to_state_record(now_msk=self.fixed_now())

        self.assertEqual(record["saved_at"], "2026-05-10T14:30:00+03:00")
        self.assertEqual(record["payload"]["auth[access_token]"], "access-secret-token")
        self.assertEqual(record["payload"]["auth[refresh_token]"], "refresh-secret-token")
        self.assertEqual(record["payload"]["auth[client_endpoint]"], "https://portal.example/rest")
        self.assertEqual(record["payload"]["auth[server_endpoint]"], "https://oauth.example/rest")
        self.assertEqual(record["summary"]["domain"], "portal.example")
        self.assertTrue(record["summary"]["auth_present"])

    def test_write_install_state_rejects_invalid_payload_without_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "Invalid payload"):
                oauth_install.write_install_state(
                    state_dir=Path(tmpdir),
                    payload=oauth_install.InstallPayload.from_json({}),
                    now_msk=self.fixed_now(),
                )

            self.assertFalse((Path(tmpdir) / "install.latest.json").exists())

    def test_write_install_state_is_atomic_and_0600(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first = oauth_install.write_install_state(
                state_dir=Path(tmpdir),
                payload=oauth_install.InstallPayload.from_json(sample_payload(DOMAIN="first.example")),
                now_msk=self.fixed_now(),
            )
            second = oauth_install.write_install_state(
                state_dir=Path(tmpdir),
                payload=oauth_install.InstallPayload.from_json(sample_payload(DOMAIN="second.example")),
                now_msk=self.fixed_now(),
            )

            self.assertEqual(first, second)
            self.assertEqual(read_state(second)["summary"]["domain"], "second.example")
            self.assertEqual(second.stat().st_mode & 0o777, 0o600)

    def test_import_json_saves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = oauth_install.import_install_state_from_stdin(
                state_dir=Path(tmpdir),
                now_msk_factory=self.fixed_now,
                stdin_text=json.dumps(sample_payload()),
            )

            self.assertEqual(read_state(path)["payload"]["auth[member_id]"], "member-1")

    def test_import_wrapped_json_saves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = oauth_install.import_install_state_from_stdin(
                state_dir=Path(tmpdir),
                now_msk_factory=self.fixed_now,
                stdin_text=json.dumps({"payload": sample_payload(member_id="member-2")}),
            )

            self.assertEqual(read_state(path)["payload"]["auth[member_id]"], "member-2")

    def test_import_form_body_saves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = oauth_install.import_install_state_from_stdin(
                state_dir=Path(tmpdir),
                now_msk_factory=self.fixed_now,
                stdin_text=form_body(sample_payload()).decode("utf-8"),
            )

            self.assertEqual(read_state(path)["summary"]["domain"], "portal.example")

    def test_import_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "Invalid JSON"):
                oauth_install.import_install_state_from_stdin(
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    stdin_text="{",
                )

    def test_import_json_array_raises_invalid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "Invalid payload"):
                oauth_install.import_install_state_from_stdin(
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    stdin_text="[]",
                )

    def test_summary_rejects_unreadable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "install.latest.json"
            path.write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "Saved state unreadable"):
                oauth_install._summary_for_stdout(path)

    def test_summary_rejects_state_without_payload_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "install.latest.json"
            path.write_text(json.dumps({"payload": []}), encoding="utf-8")

            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "Saved state invalid"):
                oauth_install._summary_for_stdout(path)

    def test_main_import_prints_only_masked_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdin = io.StringIO(json.dumps(sample_payload()))
            stdout = io.StringIO()
            with patch("sys.stdin", stdin):
                with redirect_stdout(stdout):
                    code = oauth_install.main(["import", "--state-dir", tmpdir])

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("portal.example", output)
            self.assertIn("member-1", output)
            self.assertNotIn("access-secret-token", output)
            self.assertNotIn("refresh-secret-token", output)
            self.assertNotIn(tmpdir, output)

    def test_main_serve_prints_masked_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = oauth_install.write_install_state(
                state_dir=Path(tmpdir),
                payload=oauth_install.InstallPayload.from_json(sample_payload()),
                now_msk=self.fixed_now(),
            )
            stdout = io.StringIO()
            with patch.object(oauth_install, "serve_install_handler", return_value=path) as serve:
                with redirect_stdout(stdout):
                    code = oauth_install.main(["serve", "--port", "8765", "--state-dir", tmpdir])

            self.assertEqual(code, 0)
            serve.assert_called_once()
            self.assertNotIn("access-secret-token", stdout.getvalue())

    def test_module_entrypoint_uses_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(sys, "argv", ["oauth_install.py", "import", "--state-dir", tmpdir]),
                patch("sys.stdin", io.StringIO(json.dumps(sample_payload()))),
                redirect_stdout(io.StringIO()),
                warnings.catch_warnings(),
            ):
                warnings.simplefilter("ignore", RuntimeWarning)
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_module("belberry.bitrix24.scripts.oauth_install", run_name="__main__")

        self.assertEqual(caught.exception.code, 0)

    def test_default_state_dir_uses_belberry_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"BELBERRY_BITRIX24_APP_STATE_DIR": tmpdir}, clear=True):
                self.assertEqual(oauth_install._default_state_dir(), Path(tmpdir))

    def test_default_state_dir_requires_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "BELBERRY_BITRIX24_APP_STATE_DIR"):
                oauth_install._default_state_dir()

    def test_server_rejects_public_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "host must be 127.0.0.1"):
                oauth_install.serve_install_handler(
                    port=8765,
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    host="0.0.0.0",
                    timeout_sec=1,
                )

    def test_server_rejects_external_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "host must be 127.0.0.1"):
                oauth_install.serve_install_handler(
                    port=8765,
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    host="192.168.1.1",
                    timeout_sec=1,
                )

    def test_server_rejects_privileged_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "port must be >= 1024"):
                oauth_install.serve_install_handler(
                    port=1023,
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    timeout_sec=1,
                )

    def test_server_rejects_port_over_65535(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "port must be <= 65535"):
                oauth_install.serve_install_handler(
                    port=65536,
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    timeout_sec=1,
                )

    def test_server_times_out_without_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(oauth_install.OAuthInstallError, "timeout"):
                oauth_install.serve_install_handler(
                    port=free_port(),
                    state_dir=Path(tmpdir),
                    now_msk_factory=self.fixed_now,
                    timeout_sec=0,
                )

    def test_server_empty_payload_returns_400_and_continues_until_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_server_flow(
                state_dir=Path(tmpdir),
                invalid_body=b"",
                valid_body=form_body(sample_payload()),
            )

            self.assertEqual(result["invalid_status"], 400)
            self.assertEqual(result["success_status"], 200)
            self.assertEqual(read_state(result["path"])["summary"]["domain"], "portal.example")

    def test_server_payload_without_access_token_returns_400_and_no_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_server_flow(
                state_dir=Path(tmpdir),
                invalid_body=form_body(sample_payload(AUTH_ID="")),
                valid_body=form_body(sample_payload()),
            )

            self.assertEqual(result["invalid_status"], 400)
            self.assertFalse(result["state_exists_after_invalid"])

    def test_server_payload_without_client_endpoint_returns_400_and_no_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_server_flow(
                state_dir=Path(tmpdir),
                invalid_body=form_body(sample_payload(client_endpoint="")),
                valid_body=form_body(sample_payload()),
            )

            self.assertEqual(result["invalid_status"], 400)
            self.assertFalse(result["state_exists_after_invalid"])

    def test_server_wrong_path_and_get_return_404_then_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_server_flow(
                state_dir=Path(tmpdir),
                invalid_body=form_body(sample_payload()),
                invalid_path="/wrong",
                send_get_first=True,
                valid_body=form_body(sample_payload()),
            )

            self.assertEqual(result["get_status"], 404)
            self.assertEqual(result["invalid_status"], 404)
            self.assertEqual(result["success_status"], 200)

    def test_server_success_response_does_not_leak_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_server_flow(
                state_dir=Path(tmpdir),
                invalid_body=None,
                valid_body=form_body(sample_payload()),
            )

            self.assertIn(oauth_install.SUCCESS_HTML, result["success_body"])
            self.assertNotIn("access-secret-token", result["success_body"])
            self.assertNotIn("refresh-secret-token", result["success_body"])

    def run_server_flow(
        self,
        *,
        state_dir: Path,
        invalid_body: bytes | None,
        valid_body: bytes,
        invalid_path: str = "/install",
        send_get_first: bool = False,
    ) -> dict:
        port = free_port()
        started = threading.Event()
        result: dict = {}

        def target() -> None:
            started.set()
            try:
                result["path"] = oauth_install.serve_install_handler(
                    port=port,
                    state_dir=state_dir,
                    now_msk_factory=self.fixed_now,
                    timeout_sec=5,
                )
            except BaseException as error:  # noqa: BLE001
                result["error"] = error

        thread = threading.Thread(target=target)
        thread.start()
        self.assertTrue(started.wait(timeout=1))
        self.wait_for_listener(port)

        if send_get_first:
            status, body = self.request("GET", f"http://127.0.0.1:{port}/install", None)
            result["get_status"] = status
            result["get_body"] = body

        if invalid_body is not None:
            status, body = self.request("POST", f"http://127.0.0.1:{port}{invalid_path}", invalid_body)
            result["invalid_status"] = status
            result["invalid_body"] = body
            result["state_exists_after_invalid"] = (state_dir / "install.latest.json").exists()

        status, body = self.request("POST", f"http://127.0.0.1:{port}/install", valid_body)
        result["success_status"] = status
        result["success_body"] = body
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        if "error" in result:
            raise result["error"]
        return result

    def wait_for_listener(self, port: int) -> None:
        deadline = time.monotonic() + 2
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError as error:
                last_error = error
        raise AssertionError(f"listener did not start: {last_error}")

    def request(self, method: str, url: str, body: bytes | None) -> tuple[int, str]:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
                return int(response.status), response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return int(error.code), error.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
