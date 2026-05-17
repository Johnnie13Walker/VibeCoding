from __future__ import annotations

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
