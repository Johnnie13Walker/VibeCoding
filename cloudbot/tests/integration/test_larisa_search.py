from __future__ import annotations

import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from apps.larisa_ivanovna.workflows.search import SearchWorkflowDeps, run_search_workflow
from cloudbot.orchestrator.router import select_workflow
from cloudbot.orchestrator.search_state import load_search_state, save_search_state
from cloudbot.providers import search_provider
from cloudbot.skills import web_search


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class LarisaSearchWorkflowTests(unittest.TestCase):
    def test_search_workflow_asks_for_sports_clarification(self) -> None:
        with TemporaryDirectory() as tmp_dir, patch.dict(
            os.environ,
            {"CLOUDBOT_SEARCH_STATE_PATH": f"{tmp_dir}/search_state.json"},
            clear=False,
        ):
            result = run_search_workflow(query="как сегодня сыграл ЦСКА?", chat_id="1", user_id="2")

            self.assertTrue(result["needs_clarification"])
            self.assertIn("футбольный", result["text"])
            state = load_search_state("1", "2")
            self.assertIsNotNone(state)
            self.assertEqual(state["mode"], "sports_disambiguation")

    def test_search_workflow_merges_followup_and_keeps_response_human(self) -> None:
        with TemporaryDirectory() as tmp_dir, patch.dict(
            os.environ,
            {"CLOUDBOT_SEARCH_STATE_PATH": f"{tmp_dir}/search_state.json"},
            clear=False,
        ):
            save_search_state(
                "1",
                "2",
                {
                    "mode": "sports_disambiguation",
                    "query": "как сегодня сыграл ЦСКА?",
                },
            )

            deps = SearchWorkflowDeps(
                search_runner=lambda payload, providers=None: {
                    "ok": True,
                    "provider": "duckduckgo",
                    "results": [
                        {
                            "title": "ЦСКА - Локомотив 2:1",
                            "url": "https://example.com/cska",
                            "snippet": "Матч завершился со счетом 2:1.",
                        },
                        {
                            "title": "Результат матча ЦСКА 2:1",
                            "url": "https://example.com/cska-2",
                            "snippet": "Еще один источник подтверждает 2:1.",
                        },
                    ],
                }
            )

            result = run_search_workflow(query="футбольный", chat_id="1", user_id="2", deps=deps)

            self.assertIn("2:1", result["text"])
            self.assertNotIn("Провайдер:", result["text"])
            self.assertIn("Источники:", result["text"])

    def test_router_uses_pending_search_state_for_followup(self) -> None:
        with TemporaryDirectory() as tmp_dir, patch.dict(
            os.environ,
            {"CLOUDBOT_SEARCH_STATE_PATH": f"{tmp_dir}/search_state.json"},
            clear=False,
        ):
            save_search_state(
                "11",
                "22",
                {
                    "mode": "sports_disambiguation",
                    "query": "как сегодня сыграл ЦСКА?",
                },
            )
            workflow = select_workflow({"text": "футбольный", "chat_id": "11", "user_id": "22"})
            self.assertEqual(workflow, "larisa_search")

    def test_search_workflow_simplifies_general_question(self) -> None:
        captured_queries: list[str] = []

        def fake_runner(payload, providers=None):
            captured_queries.append(str(payload.get("query") or ""))
            if str(payload.get("query") or "").strip().lower() == "openai":
                return {
                    "ok": True,
                    "provider": "duckduckgo",
                    "results": [
                        {
                            "title": "OpenAI",
                            "url": "https://openai.com",
                            "snippet": "AI research lab",
                        }
                    ],
                }
            return {"ok": True, "provider": "duckduckgo", "results": []}

        result = run_search_workflow(
            query="что такое OpenAI?",
            deps=SearchWorkflowDeps(search_runner=fake_runner),
        )

        self.assertIn("Нашла по запросу", result["text"])
        self.assertIn("openai", " ".join(captured_queries).lower())


class WebSearchSkillTests(unittest.TestCase):
    def test_web_search_forces_duckduckgo_and_normalizes_results(self) -> None:
        with patch.object(
            web_search,
            "_search_with_runtime",
            return_value=([{"title": "OpenAI", "url": "https://openai.com", "snippet": "AI"}], ""),
        ):
            result = web_search.run(
                {"query": "openai", "limit": 1},
                providers={"search": {"provider": "kimi", "kimi": {"apiKey": "secret"}}},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertEqual(result["results"][0]["url"], "https://openai.com")
        self.assertTrue(result["warnings"])

    def test_web_search_prefers_searxng_when_base_url_is_configured(self) -> None:
        with patch.object(
            web_search,
            "urlopen",
            return_value=_FakeHTTPResponse(
                {
                    "results": [
                        {
                            "title": "OpenAI",
                            "url": "https://openai.com",
                            "content": "AI research and products",
                        }
                    ]
                }
            ),
        ):
            result = web_search.run(
                {"query": "openai", "limit": 1},
                providers={"search": {"provider": "duckduckgo", "base_url": "http://searxng:8080"}},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["url"], "https://openai.com")
        self.assertFalse(any("fallback" in warning.lower() for warning in result["warnings"]))

    def test_web_search_returns_error_for_empty_query(self) -> None:
        result = web_search.run({"query": ""}, providers={"search": {"provider": "duckduckgo"}})

        self.assertFalse(result["ok"])
        self.assertIn("Пустой", result["error"])

    def test_searxng_url_skips_language_for_duckduckgo_engine(self) -> None:
        provider_url = search_provider._build_searxng_url(
            "http://searxng:8080",
            query="openai",
            engine="duckduckgo",
            limit=1,
        )
        skill_url = web_search._build_searxng_url(
            "http://searxng:8080",
            query="openai",
            engine="duckduckgo",
            limit=1,
        )

        self.assertNotIn("language=", provider_url)
        self.assertNotIn("language=", skill_url)

    def test_searxng_url_keeps_language_for_non_duckduckgo_engine(self) -> None:
        provider_url = search_provider._build_searxng_url(
            "http://searxng:8080",
            query="openai",
            engine="google",
            limit=1,
        )
        skill_url = web_search._build_searxng_url(
            "http://searxng:8080",
            query="openai",
            engine="google",
            limit=1,
        )

        self.assertIn("language=ru", provider_url)
        self.assertIn("language=ru", skill_url)


if __name__ == "__main__":
    unittest.main()
