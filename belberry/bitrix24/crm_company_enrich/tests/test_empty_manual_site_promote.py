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
