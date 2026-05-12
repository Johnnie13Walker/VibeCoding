"""Safety guard: компании c in_active_deal_merge=1 пропускаются в enrich-web и classify."""
from __future__ import annotations

from crm_company_enrich.config import TAB_QUEUE
from crm_company_enrich.models import QUEUE_HEADERS, QueueRow, TargetAction
from crm_company_enrich.state import Status
from crm_company_enrich.stages import classify, enrich_web


class FakeSheets:
    def __init__(self, rows: list[QueueRow]):
        self._rows = [r.to_sheet_row() for r in rows]
        self.updates: list[tuple[str, list[list[str]]]] = []

    def read(self, sheet: str, *args, **kwargs):
        if sheet == TAB_QUEUE:
            return [QUEUE_HEADERS, *self._rows]
        return []

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs):
        self.updates.append((range_, rows))
        if range_.startswith("A") and ":" in range_:
            n = int(range_.split(":")[0][1:])
            idx = n - 2
            if 0 <= idx < len(self._rows):
                self._rows[idx] = rows[0]

    def append(self, sheet: str, rows: list[list[str]], **kwargs):
        pass

    def ensure_sheet(self, *args, **kwargs):
        pass

    def batch_update(self, data, **kwargs):
        for entry in data:
            range_ = entry["range"].split("!", 1)[-1]
            self.update(TAB_QUEUE, range_, entry["values"])

    def clear(self, *args, **kwargs):
        pass


class BoomBitrix:
    """Любой вызов → AssertionError. Гарантия, что safety-guard перехватит до Bitrix."""

    def search_requisite_by_inn(self, inn):
        raise AssertionError(f"Bitrix.search_requisite_by_inn вызван для {inn} — guard не сработал")


def test_enrich_web_skips_active_deal_merge_rows():
    row = QueueRow(
        company_id="10",
        company_name="Active Co",
        web="example.ru",
        status=Status.NEW,
        in_active_deal_merge=True,
    )
    sheets = FakeSheets([row])

    def boom_fetcher(url):
        raise AssertionError(f"HTTP fetch вызван для активной группы: {url}")

    summary = enrich_web.run(sheets, fetcher=boom_fetcher, sleep_s=0)
    assert summary["enriched"] == 0
    assert summary["failed"] == 0
    assert summary["skipped_in_active_merge"] == 1
    assert sheets.updates == []  # никаких write в Sheets


def test_classify_skips_active_deal_merge_without_bitrix_call():
    row = QueueRow(
        company_id="10",
        discovered_inn="7707083893",
        status=Status.ENRICHED,
        in_active_deal_merge=True,
    )
    sheets = FakeSheets([row])

    summary = classify.run(BoomBitrix(), sheets)
    # Строка переведена в CLASSIFIED+SKIP_NO_INN, но без обращения к Bitrix
    assert summary["skipped_active_deal_merge"] == 1
    assert summary["classified"] == 0
    assert sheets.updates  # update в Sheets произошёл (изменён статус)
    # Убеждаемся, что target_action — именно SKIP_NO_INN
    updated_row_values = sheets.updates[0][1][0]
    headers = QUEUE_HEADERS
    target_action_idx = headers.index("target_action")
    assert updated_row_values[target_action_idx] == TargetAction.SKIP_NO_INN.value


def test_enrich_web_skips_non_new_rows_without_fetch():
    row_classified = QueueRow(
        company_id="10",
        company_name="Already classified",
        status=Status.CLASSIFIED,
        in_active_deal_merge=False,
    )
    sheets = FakeSheets([row_classified])

    def boom_fetcher(url):
        raise AssertionError("fetcher не должен вызываться для не-NEW строк")

    summary = enrich_web.run(sheets, fetcher=boom_fetcher, sleep_s=0)
    assert summary["enriched"] == 0
    assert summary["failed"] == 0
    assert summary["skipped_in_active_merge"] == 0
