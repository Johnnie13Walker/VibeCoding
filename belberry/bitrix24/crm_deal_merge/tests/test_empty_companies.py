from __future__ import annotations

from crm_deal_merge.stages import empty_companies


class FakeBitrix:
    def paginate(self, method: str, params: dict, id_field: str = "ID"):
        data = {
            "crm.company.list": [
                {"ID": "10", "TITLE": "Пустая", "ASSIGNED_BY_ID": "1", "DATE_CREATE": "2026-05-01T10:00:00+03:00"},
                {"ID": "20", "TITLE": "Со сделкой", "ASSIGNED_BY_ID": "1", "DATE_CREATE": "2026-05-02T10:00:00+03:00"},
                {"ID": "30", "TITLE": "С полезным контактом", "ASSIGNED_BY_ID": "2", "DATE_CREATE": "2026-05-03T10:00:00+03:00"},
                {"ID": "40", "TITLE": "С мусорным контактом", "ASSIGNED_BY_ID": "2", "DATE_CREATE": "2026-05-04T10:00:00+03:00"},
            ],
            "crm.contact.list": [
                {"ID": "300", "COMPANY_ID": "30", "NAME": "Анна", "LAST_NAME": "Иванова", "EMAIL": [], "POST": ""},
                {"ID": "400", "COMPANY_ID": "40", "NAME": "Без имени", "LAST_NAME": "", "EMAIL": [], "POST": ""},
            ],
            "crm.deal.list": [{"ID": "200", "COMPANY_ID": "20", "CONTACT_ID": ""}],
            "crm.lead.list": [],
            "crm.requisite.list": [],
        }
        yield from data.get(method, [])

    def batch(self, commands: dict):
        return {
            "u_1": [{"NAME": "Лариса", "LAST_NAME": "Ивановна"}],
            "u_2": [{"NAME": "Аркадий", "LAST_NAME": ""}],
        }


class FakeSheets:
    def __init__(self) -> None:
        self.write_calls: list[str] = []

    def read(self, sheet: str, range_: str = "A1:Z10000", unformatted: bool = False):
        return [
            ["old report"],
            empty_companies.HEADERS,
            ["old", "", "", "", "", "", "", "", "", "", "", "", "1"],
            ["old", "", "", "", "", "", "", "", "", "", "", "", "2"],
            ["old", "", "", "", "", "", "", "", "", "", "", "", "3"],
        ]

    def ensure_sheet(self, *args, **kwargs):
        self.write_calls.append("ensure_sheet")

    def clear(self, *args, **kwargs):
        self.write_calls.append("clear")

    def update(self, *args, **kwargs):
        self.write_calls.append("update")


def test_empty_companies_dry_run_is_read_only_and_counts_delta(capsys) -> None:
    sheets = FakeSheets()

    result = empty_companies.run(FakeBitrix(), sheets, write_sheet=False)

    assert result["dry_run"] is True
    assert result["trash_companies"] == 2
    assert result["previous_snapshot_rows"] == 3
    assert result["delta_vs_previous"] == -1
    assert result["gone_vs_previous"] == 1
    assert result["without_contacts"] == 1
    assert result["with_only_junk_contacts"] == 1
    assert sheets.write_calls == []
    assert "dry-run" in capsys.readouterr().out
