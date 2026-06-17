from __future__ import annotations

import unittest
from unittest.mock import patch

from cloudbot.devops.system_health import (
    _build_capabilities_snapshot,
    _build_integrations_snapshot,
    _check_bitrix_oauth,
    _check_google_calendar_oauth,
    _check_todoist_api,
    _check_web_search_skill,
    _check_wazzup_api,
    _check_whoop_api,
)


class SystemHealthWhoopTests(unittest.TestCase):
    def test_whoop_oauth_credentials_count_as_configured(self) -> None:
        payload = _check_whoop_api(
            {
                "WHOOP_CLIENT_ID": "client-id",
                "WHOOP_CLIENT_SECRET": "client-secret",
                "WHOOP_REFRESH_TOKEN": "refresh-token",
            }
        )

        self.assertEqual(payload["status"], "not_checked")
        self.assertIn("OAuth-контур настроен", payload["reason"])

    def test_whoop_without_token_or_oauth_is_not_configured(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_whoop_runtime_snapshot",
            return_value=None,
        ):
            payload = _check_whoop_api({})

        self.assertEqual(payload["status"], "not_configured")
        self.assertIn("WHOOP token/API key не задан", payload["reason"])

    def test_whoop_server_runtime_oauth_counts_as_configured(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_whoop_runtime_snapshot",
            return_value={
                "WHOOP_CLIENT_ID": "client-id",
                "WHOOP_CLIENT_SECRET": "client-secret",
                "WHOOP_REFRESH_TOKEN": "refresh-token",
            },
        ):
            payload = _check_whoop_api({})

        self.assertEqual(payload["status"], "not_checked")
        self.assertIn("server-only OAuth-контур настроен", payload["reason"])


class SystemHealthSearchAndWazzupTests(unittest.TestCase):
    def test_larisa_search_capability_detects_existing_route(self) -> None:
        payload = _build_capabilities_snapshot({})

        self.assertEqual(payload["Web search для Ларисы"]["status"], "ok")

    def test_wazzup_dns_failure_is_not_checked_when_env_exists(self) -> None:
        with patch(
            "cloudbot.devops.system_health.WazzupProvider.get_api_status",
            return_value={"ok": False, "status": "fail", "message": "[Errno 8] nodename nor servname provided, or not known"},
        ), patch(
            "cloudbot.devops.system_health._remote_wazzup_runtime_snapshot",
            return_value=None,
        ):
            payload = _check_wazzup_api({"WAZZUP_API_KEY": "key", "WAZZUP_API_BASE_URL": "https://api.wazzup24.com"})

        self.assertEqual(payload["status"], "not_checked")

    def test_wazzup_remote_runtime_turns_dns_failure_into_ok(self) -> None:
        with patch(
            "cloudbot.devops.system_health.WazzupProvider.get_api_status",
            return_value={"ok": False, "status": "fail", "message": "[Errno 8] nodename nor servname provided, or not known"},
        ), patch(
            "cloudbot.devops.system_health._remote_wazzup_runtime_snapshot",
            return_value={
                "api_key_present": "1",
                "api_base_url": "https://api.wazzup24.com",
                "webhook_forward_url": "https://example.com/wazzup-forward",
            },
        ):
            payload = _check_wazzup_api({"WAZZUP_API_KEY": "key", "WAZZUP_API_BASE_URL": "https://api.wazzup24.com"})

        self.assertEqual(payload["status"], "ok")

    def test_remote_runtime_marks_server_only_endpoints_as_configured(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_wazzup_runtime_snapshot",
            return_value={
                "api_key_present": "1",
                "api_base_url": "https://api.wazzup24.com",
                "webhook_forward_url": "https://example.com/wazzup-forward",
                "bitrix_webhook_url": "https://example.bitrix24.ru/rest/1/token/",
            },
        ):
            payload = _build_integrations_snapshot({}, {"status": "ok", "message": "OK"})

        self.assertEqual(payload["WAZZUP_WEBHOOK_FORWARD"]["status"], "ok")
        self.assertEqual(payload["WEBHOOK"]["status"], "ok")

    def test_bitrix_oauth_server_runtime_counts_as_configured(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_bitrix_oauth_snapshot",
            return_value={
                "path": "/opt/openclaw/state/bitrix_app/handler.latest.json",
                "saved_at": "2026-04-18T09:00:00+03:00",
                "domain": "example.bitrix24.ru",
                "member_id": "1",
                "status": "L",
            },
        ), patch(
            "cloudbot.devops.system_health.BitrixAppAuth.summary",
            return_value={"ok": False},
        ):
            payload = _check_bitrix_oauth({}, {"status": "fail", "message": "Bitrix request failed"})

        self.assertEqual(payload["status"], "not_checked")
        self.assertIn("server runtime", payload["reason"])

    def test_build_integrations_uses_bitrix_oauth_runtime_snapshot(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_bitrix_oauth_snapshot",
            return_value={
                "path": "/opt/openclaw/state/bitrix_app/handler.latest.json",
                "saved_at": "2026-04-18T09:00:00+03:00",
                "domain": "example.bitrix24.ru",
                "member_id": "1",
                "status": "L",
            },
        ), patch(
            "cloudbot.devops.system_health.BitrixAppAuth.summary",
            return_value={"ok": False},
        ):
            payload = _build_integrations_snapshot({}, {"status": "fail", "message": "Bitrix request failed"})

        self.assertEqual(payload["Bitrix OAuth"]["status"], "not_checked")

    def test_todoist_server_runtime_counts_as_configured(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_todo_runtime_snapshot",
            return_value={
                "token_present": "1",
                "state_dir": "/home/node/.openclaw/todo-integration-data",
                "snapshot_present": "1",
                "snapshot_generated_at": "2026-04-18T09:10:00+03:00",
            },
        ):
            payload = _check_todoist_api({})

        self.assertEqual(payload["status"], "not_checked")
        self.assertIn("server runtime", payload["reason"])

    def test_google_calendar_server_runtime_counts_as_known_contour(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_google_calendar_runtime_snapshot",
            return_value={
                "provider_path": "/root/.openclaw/workspace/todo-integration/src/agenda/providers/googleCalendar.mjs",
                "runtime": "legacy_todo_integration",
            },
        ):
            payload = _check_google_calendar_oauth({})

        self.assertEqual(payload["status"], "not_checked")
        self.assertIn("server runtime", payload["reason"])

    def test_build_integrations_includes_google_calendar_and_todo_runtime_status(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_bitrix_oauth_snapshot",
            return_value=None,
        ), patch(
            "cloudbot.devops.system_health.BitrixAppAuth.summary",
            return_value={"ok": False},
        ), patch(
            "cloudbot.devops.system_health._remote_todo_runtime_snapshot",
            return_value={
                "token_present": "1",
                "state_dir": "/home/node/.openclaw/todo-integration-data",
                "snapshot_present": "1",
                "snapshot_generated_at": "2026-04-18T09:10:00+03:00",
            },
        ), patch(
            "cloudbot.devops.system_health._remote_google_calendar_runtime_snapshot",
            return_value={
                "provider_path": "/root/.openclaw/workspace/todo-integration/src/agenda/providers/googleCalendar.mjs",
                "runtime": "legacy_todo_integration",
            },
        ):
            payload = _build_integrations_snapshot({}, {"status": "fail", "message": "Bitrix request failed"})

        self.assertEqual(payload["Todoist"]["status"], "not_checked")
        self.assertEqual(payload["Google Calendar OAuth"]["status"], "not_checked")

    def test_web_search_skill_dns_failure_is_not_checked(self) -> None:
        with patch(
            "cloudbot.devops.system_health.web_search_skill_run",
            return_value={"ok": False, "error": "<urlopen error [Errno 8] nodename nor servname provided, or not known>"},
        ):
            payload = _check_web_search_skill({"SEARCH_PROVIDER": "duckduckgo"})

        self.assertEqual(payload["status"], "not_checked")

    def test_search_provider_uses_remote_runtime_when_local_env_is_not_authoritative(self) -> None:
        with patch(
            "cloudbot.devops.system_health._remote_search_runtime_snapshot",
            return_value={
                "provider": "duckduckgo",
                "base_url": "http://searxng:8080",
                "engine": "duckduckgo",
                "image": "openclaw:ddg-searxng-20260412",
            },
        ):
            from cloudbot.devops.system_health import _check_web_search_provider

            payload = _check_web_search_provider({})

        self.assertEqual(payload["status"], "ok")
