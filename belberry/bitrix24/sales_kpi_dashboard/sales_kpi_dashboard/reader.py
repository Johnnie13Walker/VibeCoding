from __future__ import annotations

from sales_dashboard.bitrix_client import BitrixClient


class BitrixReader:
    def __init__(self, client: BitrixClient | None = None):
        self.client = client or BitrixClient()

    def profile(self) -> dict:
        return self.client.call("profile").get("result") or {}
