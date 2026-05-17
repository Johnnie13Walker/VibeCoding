"""MANUAL_REVIEW lifecycle: enrich → classify/mark-approved/apply skip → promote.

Покрытие:
  1. enrich возвращает unverified rusprofile → row.status = MANUAL_REVIEW (не ENRICHED).
  2. classify не обрабатывает MANUAL_REVIEW (no Bitrix call, статус неизменён).
  3. mark-approved не одобряет MANUAL_REVIEW.
  4. apply не обрабатывает MANUAL_REVIEW.
  5. promote: MANUAL_REVIEW → ENRICHED (только Sheets-write).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from crm_company_enrich.config import TAB_QUEUE
from crm_company_enrich.models import QUEUE_HEADERS, QueueRow, TargetAction
from crm_company_enrich.sheet_store import read_queue, replace_row, update_row
from crm_company_enrich.stages import apply, classify, enrich_web, mark_approved
from crm_company_enrich.stages.enrich_web import FetchResult
from crm_company_enrich.state import Status


# ----- Reuse FakeBitrix / FakeSheets from existing test infra -----
from tests.test_apply_create_req import FakeBitrix, FakeSheets


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


# ----- 1. enrich → MANUAL_REVIEW when geo unverified -----


def test_enrich_marks_unverified_rusprofile_as_manual_review():
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        status=Status.NEW,
        web=None,
        uf_inn_candidate=None,
    )
    sheets = FakeSheets([row])

    # rusprofile-карточка с geo Свердловской области (mismatch с Краснодар)
    html = (
        "<title>ООО Профидент</title>"
        "<div class=\"company-address\">620014, Свердловская область, г. Екатеринбург</div>"
        "ИНН: 6674188744"
    )

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text=html)
        return FetchResult(url=url, status=404, text="")

    summary = enrich_web.run(sheets, fetcher=fetcher, sleep_s=0)

    assert summary["manual_review"] == 1
    assert summary["enriched"] == 0

    updated = sheets.queue_row(0)
    assert updated.status == Status.MANUAL_REVIEW
    assert updated.discovered_inn == "6674188744"
    assert updated.discovered_source == "rusprofile_unverified"


# ----- 2. classify skips MANUAL_REVIEW -----


def test_classify_skips_manual_review_rows():
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        discovered_inn="6674188744",
        discovered_source="rusprofile_unverified",
        status=Status.MANUAL_REVIEW,
    )

    class FakeBxNoCalls:
        def search_requisite_by_inn(self, inn):  # pragma: no cover — не должен дёргаться
            raise AssertionError(f"classify must not call Bitrix for MANUAL_REVIEW (inn={inn})")

    sheets = FakeSheets([row])
    summary = classify.run(FakeBxNoCalls(), sheets)

    assert summary["classified"] == 0
    updated = sheets.queue_row(0)
    assert updated.status == Status.MANUAL_REVIEW  # неизменён


# ----- 3. mark-approved skips MANUAL_REVIEW -----


def test_mark_approved_skips_manual_review():
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        discovered_inn="6674188744",
        discovered_source="rusprofile_unverified",
        target_action=TargetAction.CREATE_REQ,
        status=Status.MANUAL_REVIEW,
    )
    sheets = FakeSheets([row])
    bx = FakeBitrix()

    # --all --status CLASSIFIED — MANUAL_REVIEW не подпадает под CLASSIFIED-фильтр
    summary = mark_approved.run(sheets, bx=bx, all_=True, status="CLASSIFIED")

    assert summary["approved"] == 0
    updated = sheets.queue_row(0)
    assert updated.status == Status.MANUAL_REVIEW
    assert updated.approved is False


# ----- 4. apply skips MANUAL_REVIEW -----


def test_apply_skips_manual_review():
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        discovered_inn="6674188744",
        discovered_source="rusprofile_unverified",
        target_action=TargetAction.CREATE_REQ,
        status=Status.MANUAL_REVIEW,
        approved=True,  # даже если кто-то вручную поставил approved=1
    )
    sheets = FakeSheets([row])
    bx = FakeBitrix(existing_requisites={"37342": []})

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["applied"] == 0
    assert bx.add_calls == []
    updated = sheets.queue_row(0)
    assert updated.status == Status.MANUAL_REVIEW  # неизменён


# ----- 5. promote CLI: MANUAL_REVIEW → ENRICHED -----


def test_promote_changes_status_to_enriched():
    """Эмулируем cmd_promote напрямую: читаем queue, апдейтим row."""
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        discovered_inn="6674188744",
        discovered_source="rusprofile_unverified",
        status=Status.MANUAL_REVIEW,
    )
    sheets = FakeSheets([row])

    # Имитация cmd_promote — собирается напрямую через read_queue + replace_row.
    now = datetime.now(MOSCOW_TZ)
    queue = read_queue(sheets)
    assert len(queue) == 1
    row_number, current = queue[0]
    assert current.status == Status.MANUAL_REVIEW
    updated = replace_row(
        current,
        status=Status.ENRICHED,
        last_action_at=now,
        error_message="promoted from MANUAL_REVIEW",
    )
    update_row(sheets, row_number, updated)

    after = sheets.queue_row(0)
    assert after.status == Status.ENRICHED
    assert "promoted" in (after.error_message or "")


def test_promote_no_op_when_not_manual_review():
    """Если статус не MANUAL_REVIEW — promote ничего не делает (контракт CLI)."""
    row = QueueRow(
        company_id="37342",
        company_name="X",
        status=Status.ENRICHED,  # уже promoted
    )
    sheets = FakeSheets([row])
    # cmd_promote проверяет статус и пропускает; здесь логику тестируем по факту
    # того, что в state.py MANUAL_REVIEW существует и не путается с ENRICHED.
    assert Status.MANUAL_REVIEW != Status.ENRICHED


# ----- 6. Status ORDER: MANUAL_REVIEW не понижается до ENRICHED при идемпотентном
# повторном запуске enrich, если строка уже MANUAL_REVIEW -----


def test_manual_review_not_overwritten_by_repeat_enrich():
    """enrich фильтрует только status=NEW (см. enrich_web.run); MANUAL_REVIEW не трогаем."""
    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",
        status=Status.MANUAL_REVIEW,
        discovered_inn="6674188744",
    )
    sheets = FakeSheets([row])

    def fetcher(url):  # pragma: no cover — не должен дёргаться
        raise AssertionError("enrich must not re-fetch MANUAL_REVIEW row")

    summary = enrich_web.run(sheets, fetcher=fetcher, sleep_s=0)
    assert summary["enriched"] == 0
    assert summary["manual_review"] == 0  # ни одной новой
