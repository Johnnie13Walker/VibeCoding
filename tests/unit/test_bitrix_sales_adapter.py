from __future__ import annotations

from datetime import datetime
import unittest

from cloudbot.business_day import MOSCOW_TZ
from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter


class _FakeProvider:
    def __init__(self, portal_base_url: str = "") -> None:
        self._portal_base_url = portal_base_url

    def mode(self) -> str:
        return "not_configured"

    def portal_base_url(self) -> str:
        return self._portal_base_url


class _FakeState:
    def __init__(self, *, domain: str = "", client_endpoint: str = "", server_endpoint: str = "") -> None:
        self.domain = domain
        self.client_endpoint = client_endpoint
        self.server_endpoint = server_endpoint


class _FakeAppAuth:
    def __init__(self, state: _FakeState) -> None:
        self._state = state

    def is_configured(self) -> bool:
        return True

    def load_state(self) -> _FakeState:
        return self._state


class _FakeTimelineAppAuth(_FakeAppAuth):
    def __init__(self, state: _FakeState) -> None:
        super().__init__(state)
        self.batch_calls: list[object] = []
        self.sequential_calls: list[object] = []

    def call_payload(self, method: str, params=None, *, default=None):  # noqa: ANN001
        self.batch_calls.append((method, params))
        if method != "batch":
            raise AssertionError(method)
        return {
            "result": {
                "result": {
                    "deal_101": [
                        {"ID": "1", "CREATED": "2026-03-30T12:00:00+03:00", "COMMENT": "Свежий комментарий"},
                        {"ID": "2", "CREATED": "2026-03-10T12:00:00+03:00", "COMMENT": "Старый комментарий"},
                    ],
                    "deal_202": [
                        {"ID": "3", "CREATED": "2026-03-31T09:15:00+03:00", "COMMENT": "Новый комментарий"},
                    ],
                },
                "result_error": {},
            }
        }

    def call_method(self, method: str, params=None, *, default=None):  # noqa: ANN001
        self.sequential_calls.append((method, params))
        raise AssertionError("Sequential fallback should not be used in batch success test")


class BitrixSalesAdapterPortalBaseTests(unittest.TestCase):
    def test_prefers_client_endpoint_when_state_domain_points_to_oauth_host(self) -> None:
        adapter = BitrixSalesAdapter(
            provider=_FakeProvider(""),
            app_auth=_FakeAppAuth(
                _FakeState(
                    domain="oauth.bitrix24.tech",
                    client_endpoint="https://belberrycrm.bitrix24.ru/rest",
                    server_endpoint="https://oauth.bitrix24.tech/rest",
                )
            ),
        )

        self.assertEqual(adapter.portal_base_url(), "https://belberrycrm.bitrix24.ru")

    def test_keeps_provider_portal_base_when_it_is_already_client_portal(self) -> None:
        adapter = BitrixSalesAdapter(
            provider=_FakeProvider("https://belberrycrm.bitrix24.ru/rest/1/token"),
            app_auth=_FakeAppAuth(
                _FakeState(
                    domain="oauth.bitrix24.tech",
                    client_endpoint="https://belberrycrm.bitrix24.ru/rest",
                    server_endpoint="https://oauth.bitrix24.tech/rest",
                )
            ),
        )

        self.assertEqual(adapter.portal_base_url(), "https://belberrycrm.bitrix24.ru")


class BitrixSalesAdapterTimelineCommentsTests(unittest.TestCase):
    def test_get_deal_timeline_comments_uses_batch_and_filters_old_comments(self) -> None:
        app_auth = _FakeTimelineAppAuth(
            _FakeState(
                domain="belberrycrm.bitrix24.ru",
                client_endpoint="https://belberrycrm.bitrix24.ru/rest",
                server_endpoint="https://oauth.bitrix24.tech/rest",
            )
        )
        adapter = BitrixSalesAdapter(
            provider=_FakeProvider(""),
            app_auth=app_auth,
        )

        result = adapter.get_deal_timeline_comments(
            ["101", "202"],
            since=datetime(2026, 3, 24, 0, 0, tzinfo=MOSCOW_TZ),
            limit_per_deal=20,
        )

        self.assertEqual(len(app_auth.batch_calls), 1)
        self.assertEqual(app_auth.sequential_calls, [])
        self.assertEqual([item["id"] for item in result["101"]], ["1"])
        self.assertEqual([item["id"] for item in result["202"]], ["3"])
        self.assertEqual(result["101"][0]["comment"], "Свежий комментарий")


if __name__ == "__main__":
    unittest.main()
