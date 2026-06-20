from __future__ import annotations

import csv

from crm_company_enrich.stages import dedupe_contacts


def _contact(contact_id: str, **overrides) -> dict:
    data = {
        "ID": contact_id,
        "LAST_NAME": "Иванов",
        "NAME": "Иван",
        "SECOND_NAME": "",
        "PHONE": [],
        "EMAIL": [],
        "DATE_CREATE": f"2026-05-17T10:00:{int(contact_id):02d}+03:00",
    }
    data.update(overrides)
    return data


def test_normalize_name_strips_leading_bang():
    contact = _contact("1", LAST_NAME="!", NAME="Решетников Александр Сергеевич")

    assert dedupe_contacts._normalize_name(contact) == "решетников александр сергеевич"


def test_placeholder_clusters_with_real_by_name_alone():
    placeholder = _contact("1", LAST_NAME="!", NAME="Иванов Иван")
    real = _contact("2", LAST_NAME="Иванов", NAME="Иван")

    clusters = dedupe_contacts._cluster_duplicates([placeholder, real])

    assert [[c["ID"] for c in cluster] for cluster in clusters] == [["1", "2"]]
    assert dedupe_contacts._cluster_match_reasons(clusters[0]) == ["name", "placeholder_dedup"]


def test_placeholder_does_not_cluster_homonyms_when_both_real():
    first = _contact("1", LAST_NAME="Иванов", NAME="Иван")
    second = _contact("2", LAST_NAME="Иванов", NAME="Иван")

    clusters = dedupe_contacts._cluster_duplicates([first, second])

    assert sorted(len(cluster) for cluster in clusters) == [1, 1]


def test_director_bang_contact_is_not_placeholder():
    director = _contact("1", LAST_NAME="!", NAME="Лагойский Дмитрий Владимирович", POST="ГЕНЕРАЛЬНЫЙ ДИРЕКТОР")
    real = _contact("2", LAST_NAME="Лагойский", NAME="Дмитрий", SECOND_NAME="Владимирович")

    clusters = dedupe_contacts._cluster_duplicates([director, real])

    assert dedupe_contacts._is_placeholder_contact(director) is False
    assert sorted(len(cluster) for cluster in clusters) == [1, 1]


def test_winner_is_non_placeholder():
    placeholder = _contact(
        "1",
        LAST_NAME="!",
        NAME="Решетников Александр Сергеевич",
        PHONE=[{"VALUE": "+7 985 472-42-52"}],
    )
    real = _contact("2", LAST_NAME="Решетников", NAME="Александр", SECOND_NAME="Сергеевич")

    winner = dedupe_contacts._pick_winner([placeholder, real], {"1": [], "2": []})

    assert winner["ID"] == "2"


def test_merge_drops_placeholder_phone_email():
    winner = _contact(
        "75772",
        LAST_NAME="Решетников",
        NAME="Александр",
        SECOND_NAME="Сергеевич",
        PHONE=[{"VALUE": "+79104335482", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
        EMAIL=[{"VALUE": "DOKASRESH@MAIL.RU", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
    )
    placeholder = _contact(
        "75774",
        LAST_NAME="!",
        NAME="Решетников Александр Сергеевич",
        PHONE=[{"VALUE": "+7 985 472-42-52", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
        EMAIL=[{"VALUE": "tv2608@mail.ru", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
    )

    assert dedupe_contacts._merged_contact_fields(winner, placeholder) == {}


def test_merge_keeps_placeholder_deal_binding(monkeypatch):
    class FakeBitrix:
        def __init__(self):
            self.updated_contacts = []
            self.added_deal_contacts = []
            self.removed_deal_contacts = []
            self.removed_company_contacts = []
            self.deleted_contacts = []

        def update_contact(self, contact_id, fields):
            self.updated_contacts.append((contact_id, fields))
            return True

        def list_deal_contacts(self, deal_id):
            return [{"CONTACT_ID": "75774"}]

        def add_deal_contact(self, deal_id, contact_id):
            self.added_deal_contacts.append((deal_id, contact_id))
            return True

        def remove_deal_contact_relation(self, deal_id, contact_id):
            self.removed_deal_contacts.append((deal_id, contact_id))
            return True

        def remove_contact_company_relation(self, contact_id, company_id):
            self.removed_company_contacts.append((contact_id, company_id))
            return True

        def delete_contact(self, contact_id):
            self.deleted_contacts.append(contact_id)
            return True

    monkeypatch.setattr(dedupe_contacts, "_backup_contact", lambda *a, **k: "")
    bx = FakeBitrix()
    winner = _contact("75772", LAST_NAME="Решетников", NAME="Александр", SECOND_NAME="Сергеевич")
    placeholder = _contact("75774", LAST_NAME="!", NAME="Решетников Александр Сергеевич")

    dedupe_contacts._merge_contact_into_winner(
        bx,
        winner=winner,
        loser=placeholder,
        company_id="17658",
        loser_deals=[{"ID": "24318"}],
        dry_run=False,
    )

    assert bx.updated_contacts == []
    assert bx.added_deal_contacts == [("24318", "75772")]
    assert bx.removed_deal_contacts == [("24318", "75774")]
    assert bx.removed_company_contacts == [("75774", "17658")]
    assert bx.deleted_contacts == ["75774"]


def test_director_cluster_is_unresolved_instead_of_deleted():
    class FakeBitrix:
        def list_contact_deals(self, contact_id):
            return []

        def list_contact_companies(self, contact_id):
            return ["100"]

    director = _contact("1", LAST_NAME="!", NAME="Лагойский Дмитрий Владимирович", POST="ГЕНЕРАЛЬНЫЙ ДИРЕКТОР")
    real = _contact("2", LAST_NAME="Лагойский", NAME="Дмитрий", SECOND_NAME="Владимирович", POST="ГЕНЕРАЛЬНЫЙ ДИРЕКТОР")

    outcome = dedupe_contacts._process_cluster(FakeBitrix(), "100", [director, real], dry_run=False)

    assert outcome.status == "UNRESOLVED"
    assert outcome.skipped_reason == "director_contact_protected"


def test_sales_deal_contact_is_unresolved_instead_of_deleted():
    """Контакт на сделке вне телемаркетинга ([10] Продажи) не должен удаляться."""
    deleted: list[str] = []

    class FakeBitrix:
        def list_contact_deals(self, contact_id):
            if contact_id == "2":
                return [{"ID": "16268", "CATEGORY_ID": "10", "STAGE_ID": "C10:1"}]
            return []

        def list_contact_companies(self, contact_id):
            return ["100"]

        def delete_contact(self, contact_id):
            deleted.append(str(contact_id))
            return True

    older = _contact("1", LAST_NAME="", NAME="Николай", PHONE=[{"VALUE": "+79639990913"}])
    on_deal = _contact("2", LAST_NAME="", NAME="Николай", PHONE=[{"VALUE": "+79639990913"}])

    outcome = dedupe_contacts._process_cluster(FakeBitrix(), "100", [older, on_deal], dry_run=False)

    assert outcome.status == "UNRESOLVED"
    assert outcome.skipped_reason.startswith("non_telemarketing_deal:")
    assert deleted == []


def test_telemarketing_only_deal_still_merges():
    """Кластер чисто телемаркетинговых сделок [50] по-прежнему сливается."""

    class FakeBitrix:
        def list_contact_deals(self, contact_id):
            return [{"ID": "900", "CATEGORY_ID": "50", "STAGE_ID": "C50:NEW"}]

        def list_contact_companies(self, contact_id):
            return ["100"]

    reason = dedupe_contacts._non_telemarketing_deal_reason(
        {"1": [{"ID": "900", "CATEGORY_ID": "50"}], "2": []}
    )
    assert reason == ""


class FakeBitrixForRun:
    def __init__(
        self,
        *,
        contacts: list[dict],
        contact_deals: dict[str, list[dict]] | None = None,
        deal_contacts: dict[str, list[dict]] | None = None,
        company_deals: list[dict] | None = None,
    ):
        self.contacts = contacts
        self.contact_deals = contact_deals or {}
        self.deal_contacts = deal_contacts or {}
        self.company_deals = company_deals or []
        self.added_deal_contacts: list[tuple[str, str]] = []
        self.removed_deal_contacts: list[tuple[str, str]] = []
        self.removed_company_contacts: list[tuple[str, str]] = []
        self.deleted_contacts: list[str] = []
        self.updated_contacts: list[tuple[str, dict]] = []
        self.timeline_comments: list[dict] = []

    def list_company_contacts_full(self, company_id):
        return list(self.contacts)

    def list_contact_deals(self, contact_id):
        return list(self.contact_deals.get(str(contact_id), []))

    def list_contact_companies(self, contact_id):
        return ["100"]

    def list_company_deals(self, company_id):
        return list(self.company_deals)

    def get_company_contacts(self, company_id):
        return [str(c["ID"]) for c in self.contacts]

    def get_contact(self, contact_id):
        for contact in self.contacts:
            if str(contact["ID"]) == str(contact_id):
                return contact
        return None

    def list_deal_contacts(self, deal_id):
        return list(self.deal_contacts.get(str(deal_id), []))

    def add_deal_contact(self, deal_id, contact_id):
        self.added_deal_contacts.append((str(deal_id), str(contact_id)))
        self.deal_contacts.setdefault(str(deal_id), []).append({"CONTACT_ID": str(contact_id)})
        return True

    def remove_deal_contact_relation(self, deal_id, contact_id):
        self.removed_deal_contacts.append((str(deal_id), str(contact_id)))
        current = self.deal_contacts.get(str(deal_id), [])
        self.deal_contacts[str(deal_id)] = [
            item for item in current
            if str(item.get("CONTACT_ID") or item.get("ID")) != str(contact_id)
        ]
        return True

    def remove_contact_company_relation(self, contact_id, company_id):
        self.removed_company_contacts.append((str(contact_id), str(company_id)))
        return True

    def delete_contact(self, contact_id):
        self.deleted_contacts.append(str(contact_id))
        return True

    def update_contact(self, contact_id, fields):
        self.updated_contacts.append((str(contact_id), dict(fields)))
        return True

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline_comments.append(
            {"owner_type_id": owner_type_id, "owner_id": str(owner_id), "text": text}
        )
        return "timeline-1"


def _placeholder_pair_with_extra_reals():
    return [
        _contact("1", LAST_NAME="!", NAME="Пенаев Арслан Агаевич"),
        _contact("2", LAST_NAME="", NAME="Пенаев Арслан Агаевич"),
        _contact("3", LAST_NAME="Сергей", NAME="Сергей"),
        _contact("4", LAST_NAME="Юмудов", NAME="Мекан"),
        _contact("5", LAST_NAME="Пенаева", NAME="Сельби"),
    ]


def _open_c50_deal(deal_id="22790"):
    return {"ID": deal_id, "CATEGORY_ID": "50", "STAGE_ID": "C50:NEW", "CLOSED": "N"}


def test_attach_unrelated_default_is_false(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", tmp_path / "audit.csv")
    bx = FakeBitrixForRun(
        contacts=_placeholder_pair_with_extra_reals(),
        contact_deals={"1": [{"ID": "22790"}]},
        deal_contacts={"22790": [{"CONTACT_ID": "1"}, {"CONTACT_ID": "2"}]},
        company_deals=[_open_c50_deal()],
    )

    summary = dedupe_contacts.run_company(bx, company_id="100", dry_run=True)

    outcome = summary["outcomes"][0]
    assert outcome["winner_contact_id"] == "2"
    assert outcome["deals_with_added_contacts"] == {}
    assert "3" not in str(outcome["deals_with_added_contacts"])
    assert "4" not in str(outcome["deals_with_added_contacts"])
    assert "5" not in str(outcome["deals_with_added_contacts"])


def test_attach_unrelated_true_legacy_behavior(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", tmp_path / "audit.csv")
    bx = FakeBitrixForRun(
        contacts=_placeholder_pair_with_extra_reals(),
        contact_deals={"1": [{"ID": "22790"}]},
        deal_contacts={"22790": [{"CONTACT_ID": "1"}, {"CONTACT_ID": "2"}]},
        company_deals=[_open_c50_deal()],
    )

    summary = dedupe_contacts.run_company(
        bx,
        company_id="100",
        dry_run=True,
        attach_unrelated_company_contacts=True,
    )

    assert summary["outcomes"][0]["deals_with_added_contacts"] == {
        "22790": ["3", "4", "5"]
    }


def test_attach_unrelated_false_with_multiple_reals(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", tmp_path / "audit.csv")
    bx = FakeBitrixForRun(
        contacts=_placeholder_pair_with_extra_reals(),
        contact_deals={"1": [{"ID": "22790"}]},
        deal_contacts={"22790": [{"CONTACT_ID": "2"}]},
        company_deals=[_open_c50_deal()],
    )

    summary = dedupe_contacts.run_company(bx, company_id="100", dry_run=True)

    added = summary["outcomes"][0]["deals_with_added_contacts"]
    assert added in ({}, {"22790": ["2"]})
    assert "3" not in str(added)
    assert "4" not in str(added)
    assert "5" not in str(added)


def test_audit_csv_row_written_on_dry_run(tmp_path, monkeypatch):
    audit_path = tmp_path / "dedupe_contacts.csv"
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", audit_path)
    bx = FakeBitrixForRun(
        contacts=[
            _contact("1", LAST_NAME="!", NAME="Иванов Иван"),
            _contact("2", LAST_NAME="Иванов", NAME="Иван"),
        ],
    )

    dedupe_contacts.run_company(bx, company_id="100", dry_run=True)

    rows = list(csv.DictReader(audit_path.open(encoding="utf-8")))
    assert rows[-1]["dry_run"] == "true"
    assert rows[-1]["status"] == "DRY_RUN"
    assert rows[-1]["source"] == "placeholder_dedup"


def test_audit_csv_row_written_on_success(tmp_path, monkeypatch):
    audit_path = tmp_path / "dedupe_contacts.csv"
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", audit_path)
    monkeypatch.setattr(dedupe_contacts, "_backup_contact", lambda *a, **k: "")
    bx = FakeBitrixForRun(
        contacts=[
            _contact("1", LAST_NAME="!", NAME="Иванов Иван"),
            _contact("2", LAST_NAME="Иванов", NAME="Иван"),
        ],
    )

    dedupe_contacts.run_company(bx, company_id="100", dry_run=False)

    rows = list(csv.DictReader(audit_path.open(encoding="utf-8")))
    assert rows[-1]["dry_run"] == "false"
    assert rows[-1]["status"] == "SUCCESS"
    assert rows[-1]["winner_contact_id"] == "2"


def test_timeline_comment_on_deal_when_loser_transferred(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", tmp_path / "audit.csv")
    monkeypatch.setattr(dedupe_contacts, "_backup_contact", lambda *a, **k: "")
    bx = FakeBitrixForRun(
        contacts=[
            _contact("1", LAST_NAME="!", NAME="Иванов Иван"),
            _contact("2", LAST_NAME="Иванов", NAME="Иван"),
        ],
        contact_deals={"1": [{"ID": "22790"}]},
        deal_contacts={"22790": [{"CONTACT_ID": "1"}]},
    )

    dedupe_contacts.run_company(bx, company_id="100", dry_run=False)

    assert bx.added_deal_contacts == [("22790", "2")]
    assert len(bx.timeline_comments) == 1
    comment = bx.timeline_comments[0]
    assert comment["owner_type_id"] == 2
    assert comment["owner_id"] == "22790"
    assert "[dedupe] Слит placeholder-контакт 1 в 2" in comment["text"]


def test_no_timeline_comment_when_winner_already_attached(tmp_path, monkeypatch):
    monkeypatch.setattr(dedupe_contacts, "AUDIT_CSV_PATH", tmp_path / "audit.csv")
    monkeypatch.setattr(dedupe_contacts, "_backup_contact", lambda *a, **k: "")
    bx = FakeBitrixForRun(
        contacts=[
            _contact("1", LAST_NAME="!", NAME="Иванов Иван"),
            _contact("2", LAST_NAME="Иванов", NAME="Иван"),
        ],
        contact_deals={"1": [{"ID": "22790"}]},
        deal_contacts={"22790": [{"CONTACT_ID": "1"}, {"CONTACT_ID": "2"}]},
    )

    dedupe_contacts.run_company(bx, company_id="100", dry_run=False)

    assert bx.added_deal_contacts == []
    assert bx.timeline_comments == []
