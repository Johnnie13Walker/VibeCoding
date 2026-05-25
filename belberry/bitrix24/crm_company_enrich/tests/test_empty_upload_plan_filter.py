"""run_upload_plan фильтрует COMPANY_DELETED, чтобы broken-link rows не возвращались в Sheet."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from crm_company_enrich.stages import enrich_empty_companies as stage


class _FakeSheets:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str, list]] = []
        self.cleared: list[str] = []

    def ensure_sheet(self, name: str) -> None:  # pragma: no cover — trivial
        pass

    def clear(self, name: str) -> None:
        self.cleared.append(name)

    def update(self, name: str, rng: str, payload: list, value_input_option: str | None = None) -> None:
        self.updates.append((name, rng, payload))


def _state_with(rows: list[dict]) -> dict:
    return {"results": rows}


def _row(company_id: str, classification: str, apply_status: str = "", inn: str = "") -> dict:
    return {
        "company_id": company_id,
        "title": f"Компания {company_id}",
        "score": 3,
        "source": "",
        "inn_candidate": inn,
        "geo_verified": False,
        "brand_predicted": "",
        "brand_evidence": "",
        "classification": classification,
        "evidence": {},
        "apply_status": apply_status,
    }


def test_run_upload_plan_excludes_company_deleted(monkeypatch, tmp_path: Path) -> None:
    """REGRESSION: COMPANY_DELETED row не должна попадать в Sheet — ссылка broken."""
    state = _state_with([
        _row("100", "READY_TO_APPLY", apply_status=""),
        _row("200", "READY_TO_APPLY", apply_status="APPLIED"),
        _row("300", "READY_TO_APPLY", apply_status="COMPANY_DELETED"),
        _row("400", "NO_INN_FOUND", apply_status=""),
        _row("500", "NO_INN_FOUND", apply_status="COMPANY_DELETED"),
        _row("600", "MANUAL", apply_status="COMPANY_DELETED"),
    ])
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")

    fake = _FakeSheets()
    monkeypatch.setattr(stage, "STATE_JSON", state_file)
    monkeypatch.setattr(stage, "_sheets", lambda: fake)

    summary = stage.run_upload_plan()

    # uploaded = только row 100 (READY empty) + row 400 (NO_INN empty)
    assert summary["uploaded"] == 2
    assert summary["hidden_applied"] == 1  # row 200
    assert summary["hidden_company_deleted"] == 3  # rows 300, 500, 600

    # Sheet получил только 2 data-row (плюс header)
    data_updates = [u for u in fake.updates if u[1].startswith("A2:")]
    assert len(data_updates) == 1
    chunk_payload = data_updates[0][2]
    assert len(chunk_payload) == 2
    # Проверяем что в payload есть ссылки на 100 и 400, нет на 300/500/600
    sheet_text = json.dumps(chunk_payload, ensure_ascii=False)
    assert "details/100/" in sheet_text
    assert "details/400/" in sheet_text
    assert "details/300/" not in sheet_text
    assert "details/500/" not in sheet_text
    assert "details/600/" not in sheet_text


def test_upload_plan_hidden_statuses_constant() -> None:
    """Контракт: COMPANY_DELETED входит в hidden statuses."""
    assert "APPLIED" in stage.UPLOAD_PLAN_HIDDEN_STATUSES
    assert "APPLIED_LIQUIDATED" in stage.UPLOAD_PLAN_HIDDEN_STATUSES
    assert "COMPANY_DELETED" in stage.UPLOAD_PLAN_HIDDEN_STATUSES
