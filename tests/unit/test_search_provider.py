from __future__ import annotations

import unittest
from unittest.mock import patch
import json

from cloudbot.providers import search_provider


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class SearchProviderTests(unittest.TestCase):
    def test_healthcheck_forces_duckduckgo_for_legacy_provider(self) -> None:
        result = search_provider.healthcheck({"provider": "kimi", "kimi": {"apiKey": "secret"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertIn("duckduckgo", " ".join(result["warnings"]))
        self.assertEqual(result["config"]["provider"], "duckduckgo")

    def test_healthcheck_keeps_duckduckgo_without_provider_warnings(self) -> None:
        result = search_provider.healthcheck({"provider": "duckduckgo"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertFalse(any("provider=" in warning for warning in result["warnings"]))

    def test_healthcheck_probes_searxng_when_base_url_is_configured(self) -> None:
        with patch.object(
            search_provider,
            "urlopen",
            return_value=_FakeHTTPResponse({"results": [{"url": "https://openai.com"}]}),
        ) as mocked_urlopen:
            result = search_provider.healthcheck(
                {
                    "provider": "duckduckgo",
                    "base_url": "http://searxng:8080",
                    "engine": "duckduckgo",
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["probe"]["result_count"], 1)
        self.assertEqual(result["probe"]["base_url"], "http://searxng:8080")
        mocked_urlopen.assert_called_once()
