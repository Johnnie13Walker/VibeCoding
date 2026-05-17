from __future__ import annotations

from crm_company_enrich.stages import enrich_empty_companies as stage


class FakeSheets:
    def __init__(self, rows):
        self._rows = rows

    def read(self, sheet, range_, unformatted=False):
        assert sheet == stage.TAB_MANUAL_SITE
        assert range_ == "A1:L10000"
        assert unformatted is False
        return self._rows


class FakeBitrix:
    def __init__(self, *args, **kwargs):
        self.updated = []

    def get_company(self, company_id):
        return {"ID": company_id}

    def list_company_requisites(self, company_id):
        return []

    def update_company(self, company_id, fields):
        self.updated.append((company_id, fields))
        return True


def test_read_manual_site_approved_falls_back_to_state_order(monkeypatch):
    monkeypatch.setattr(
        stage,
        "_load_state",
        lambda: {
            "results": [
                {
                    "company_id": "614",
                    "title": "Клиника Диагностика на Ленинском проспекте",
                    "score": 3,
                    "classification": "NO_INN_FOUND",
                    "apply_status": "",
                    "evidence": {
                        "signals": {
                            "phone": "+74997200005",
                            "domain": "zdorovje.ru",
                        }
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        stage,
        "_sheets",
        lambda: FakeSheets(
            [
                stage.MANUAL_SITE_HEADERS,
                [
                    "Клиника Диагностика на Ленинском проспекте",
                    "3",
                    "74997200005",
                    "zdorovje.ru",
                    "",
                    "поиск",
                    "поиск",
                    "zdorovje.ru",
                    "7734057525",
                    "Belberry",
                    "да",
                    "ручная проверка",
                ],
            ]
        ),
    )

    assert stage._read_manual_site_approved() == [
        {
            "company_id": "614",
            "new_site": "zdorovje.ru",
            "inn": "7734057525",
            "brand": "Belberry",
            "note": "ручная проверка",
        }
    ]


def test_read_manual_site_approved_rejects_shifted_fallback(monkeypatch):
    monkeypatch.setattr(
        stage,
        "_load_state",
        lambda: {
            "results": [
                {
                    "company_id": "614",
                    "title": "Клиника Диагностика на Ленинском проспекте",
                    "score": 3,
                    "classification": "NO_INN_FOUND",
                    "apply_status": "",
                    "evidence": {
                        "signals": {
                            "phone": "+74997200005",
                            "domain": "zdorovje.ru",
                        }
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        stage,
        "_sheets",
        lambda: FakeSheets(
            [
                stage.MANUAL_SITE_HEADERS,
                [
                    "Другая компания",
                    "3",
                    "74997200005",
                    "wrong.ru",
                    "",
                    "поиск",
                    "поиск",
                    "wrong.ru",
                    "7734057525",
                    "Belberry",
                    "да",
                    "ручная проверка",
                ],
            ]
        ),
    )

    assert stage._read_manual_site_approved() == []


def test_extract_company_id_does_not_parse_digits_from_plain_name():
    assert stage._extract_company_id("мсч.50.мвд.рф") == ""
    assert stage._extract_company_id("Имадент стоматология (ооо медсервис-85)") == ""
    assert (
        stage._extract_company_id(
            '=HYPERLINK("https://belberrycrm.bitrix24.ru/crm/company/details/4936/";"Hartmann")'
        )
        == "4936"
    )


def test_manual_site_targets_keep_failed_manual_site_until_applied(monkeypatch):
    monkeypatch.setattr(
        stage,
        "_load_state",
        lambda: {
            "results": [
                {
                    "company_id": "10",
                    "title": "Успешная",
                    "score": 3,
                    "classification": "READY_TO_APPLY",
                    "source": "manual_site",
                    "apply_status": "APPLIED",
                    "evidence": {"signals": {}},
                },
                {
                    "company_id": "20",
                    "title": "Не прошёл BP",
                    "score": 3,
                    "classification": "READY_TO_APPLY",
                    "source": "manual_site",
                    "apply_status": "BP_FAILED",
                    "inn_candidate": "7707083893",
                    "brand_predicted": "Belberry",
                    "evidence": {
                        "signals": {"domain": "example.ru"},
                        "manual_site": {
                            "new_site": "example.ru",
                            "inn": "7707083893",
                            "brand": "Belberry",
                            "note": "ручная проверка",
                        },
                    },
                },
                {
                    "company_id": "30",
                    "title": "Новая ручная",
                    "score": 2,
                    "classification": "NO_INN_FOUND",
                    "apply_status": "",
                    "evidence": {"signals": {}},
                },
            ]
        },
    )

    targets = stage._manual_site_targets()
    assert [r.company_id for r in targets] == ["20", "30"]

    failed_row = stage._manual_site_row(targets[0])
    assert failed_row[7:12] == [
        "example.ru",
        "7707083893",
        "Belberry",
        "да",
        "BP_FAILED: ручная проверка",
    ]


def test_manual_site_promote_skips_unchanged_failed_rows(monkeypatch):
    state = {
        "results": [
            {
                "company_id": "20",
                "title": "Не прошёл BP",
                "score": 3,
                "classification": "READY_TO_APPLY",
                "source": "manual_site",
                "apply_status": "BP_FAILED",
                "inn_candidate": "7707083893",
                "brand_predicted": "Belberry",
                "evidence": {
                    "signals": {"domain": "example.ru"},
                    "manual_site": {
                        "new_site": "example.ru",
                        "inn": "7707083893",
                        "brand": "Belberry",
                        "note": "ручная проверка",
                    },
                },
            },
            {
                "company_id": "30",
                "title": "Новая ручная",
                "score": 2,
                "classification": "NO_INN_FOUND",
                "apply_status": "",
                "evidence": {"signals": {"domain": "new.ru"}},
            },
        ]
    }
    monkeypatch.setattr(stage, "_load_state", lambda: state)
    monkeypatch.setattr(stage, "BitrixClient", FakeBitrix)
    monkeypatch.setattr(stage, "_backup_before_apply_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(stage, "run_upload_plan", lambda: None)
    monkeypatch.setattr(stage, "run_manual_site_sheet", lambda: None)
    monkeypatch.setattr(stage, "_write_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        stage,
        "_sheets",
        lambda: FakeSheets(
            [
                stage.MANUAL_SITE_HEADERS,
                [
                    "Не прошёл BP",
                    "3",
                    "",
                    "example.ru",
                    "",
                    "поиск",
                    "поиск",
                    "example.ru",
                    "7707083893",
                    "Belberry",
                    "да",
                    "ручная проверка",
                ],
                [
                    "Новая ручная",
                    "2",
                    "",
                    "new.ru",
                    "",
                    "поиск",
                    "поиск",
                    "new.ru",
                    "7729714623",
                    "Belberry",
                    "да",
                    "ручная проверка",
                ],
            ]
        ),
    )

    summary = stage.run_manual_site_promote(dry_run=False)

    assert summary["approved_rows"] == 2
    assert summary["promoted"] == 1
    assert summary["skipped_existing_failed"] == 1
    assert state["results"][0]["apply_status"] == "BP_FAILED"
    assert state["results"][1]["apply_status"] == ""


class FakeApplyBitrix:
    def __init__(
        self,
        *,
        initial_requisites=None,
        verified_requisites=None,
        organization_status="8850",
    ):
        self.requisites = list(initial_requisites or [])
        self.verified_requisites = list(verified_requisites or [])
        self.organization_status = organization_status
        self.workflow_calls = []
        self.updated_companies = []
        self.added_requisites = []
        self.deleted_requisites = []

    def get_company(self, company_id):
        return {
            "ID": company_id,
            "TITLE": "Тестовая компания",
            "UF_CRM_ORG_STATUS": self.organization_status,
            "INDUSTRY": "",
            "REVENUE": "1000",
        }

    def list_company_requisites(self, company_id):
        if self.verified_requisites and any(tpl == 8612 for tpl, _ in self.workflow_calls):
            return list(self.verified_requisites)
        return list(self.requisites)

    def add_requisite(self, payload):
        self.added_requisites.append(payload)
        req_id = str(7000 + len(self.added_requisites))
        self.requisites.append({"ID": req_id, "RQ_INN": payload["RQ_INN"]})
        return req_id

    def start_workflow(self, template_id, document_type):
        self.workflow_calls.append((int(template_id), list(document_type)))
        return {"workflow_id": f"wf-{template_id}"}

    def update_company(self, company_id, fields):
        self.updated_companies.append((company_id, fields))
        return True

    def delete_requisite(self, requisite_id):
        self.deleted_requisites.append(str(requisite_id))
        return True


def _apply_state():
    return {
        "results": [
            {
                "company_id": "10",
                "title": "Тестовая компания",
                "score": 3,
                "source": "manual_site",
                "inn_candidate": "7707083893",
                "geo_verified": True,
                "brand_predicted": "Belberry",
                "brand_evidence": "test",
                "classification": "READY_TO_APPLY",
                "evidence": {"signals": {}},
                "apply_status": "",
            }
        ]
    }


def _patch_apply_io(monkeypatch, fake_bx):
    monkeypatch.setattr(stage, "BitrixClient", lambda *args, **kwargs: fake_bx)
    monkeypatch.setattr(stage, "_load_state", _apply_state)
    monkeypatch.setattr(stage, "_write_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(stage, "run_upload_plan", lambda: None)
    monkeypatch.setattr(stage, "_backup_before_apply_snapshot", lambda *args, **kwargs: "backup.json")
    monkeypatch.setattr(stage.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(stage, "CCE_BIZPROC_WAIT_S", 1)
    monkeypatch.setattr(stage, "CCE_COMPANY_TOUCH", False)


def test_empty_apply_first_requisite_starts_both_bp_in_order(monkeypatch):
    fake_bx = FakeApplyBitrix(
        initial_requisites=[],
        verified_requisites=[
            {"ID": "8001", "RQ_INN": "7707083893", "RQ_KPP": "770701001", "RQ_OGRN": "1027700132195"}
        ],
    )
    _patch_apply_io(monkeypatch, fake_bx)

    summary = stage.run_apply(dry_run=False)

    assert summary["applied"] == 1
    assert [call[0] for call in fake_bx.workflow_calls[:2]] == [5938, 8612]


def test_empty_apply_existing_requisite_starts_only_update_bp(monkeypatch):
    fake_bx = FakeApplyBitrix(
        initial_requisites=[{"ID": "7001", "RQ_INN": "7707083893"}],
        verified_requisites=[
            {"ID": "8001", "RQ_INN": "7707083893", "RQ_KPP": "770701001", "RQ_OGRN": "1027700132195"}
        ],
    )
    _patch_apply_io(monkeypatch, fake_bx)

    summary = stage.run_apply(dry_run=False)

    assert summary["applied"] == 1
    assert [call[0] for call in fake_bx.workflow_calls] == [8612]


def test_empty_apply_liquidated_status_is_valid_without_retry(monkeypatch):
    fake_bx = FakeApplyBitrix(
        initial_requisites=[],
        verified_requisites=[],
        organization_status="8852",
    )
    _patch_apply_io(monkeypatch, fake_bx)

    summary = stage.run_apply(dry_run=False)

    assert summary["applied"] == 1
    assert summary["applied_liquidated"] == 1
    assert [call[0] for call in fake_bx.workflow_calls] == [5938, 8612]


def test_verify_retry_restarts_only_update_bp(monkeypatch):
    fake_bx = FakeApplyBitrix(initial_requisites=[])
    monkeypatch.setattr(stage.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(stage, "CCE_COMPANY_TOUCH", False)

    verified, requisite, apply_status = stage._verify_with_retries(fake_bx, "10")

    assert verified is False
    assert requisite is None
    assert apply_status == "BP_FAILED"
    assert [call[0] for call in fake_bx.workflow_calls] == [8612, 8612]
