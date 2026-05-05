from __future__ import annotations

import unittest

from scripts.bitrix_sync_deal_company_contacts import build_sync_plan, sync_deal_company_contacts


class _FakeAuth:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_method(self, method: str, params: dict[str, object], default: object | None = None) -> object:
        self.calls.append((method, params))
        if method == "crm.deal.get":
            return {"ID": "204", "TITLE": "koleno.su", "COMPANY_ID": "0"}
        raise AssertionError(f"Неожиданный вызов Bitrix API: {method}")


class BitrixSyncDealCompanyContactsTests(unittest.TestCase):
    def test_adds_missing_company_contacts_without_removing_existing_deal_contacts(self) -> None:
        plan = build_sync_plan(
            deal_id="23078",
            company_id="1516",
            company_contact_items=[
                {"CONTACT_ID": 3350, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
                {"CONTACT_ID": 20094, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "N"},
                {"CONTACT_ID": 1756, "SORT": 30, "ROLE_ID": 0, "IS_PRIMARY": "N"},
            ],
            deal_contact_items=[
                {"CONTACT_ID": 3350, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
                {"CONTACT_ID": 20094, "SORT": 50, "ROLE_ID": 0, "IS_PRIMARY": "N"},
            ],
        )

        self.assertEqual(plan["existing_deal_contact_ids"], ["3350", "20094"])
        self.assertEqual(plan["skipped_existing_contact_ids"], ["3350", "20094"])
        self.assertEqual(
            plan["additions"],
            [{"CONTACT_ID": 1756, "SORT": 60, "ROLE_ID": 0, "IS_PRIMARY": "N"}],
        )

    def test_first_added_contact_becomes_primary_only_when_deal_has_no_contacts(self) -> None:
        plan = build_sync_plan(
            deal_id="1",
            company_id="2",
            company_contact_items=[
                {"CONTACT_ID": "10", "SORT": "20", "IS_PRIMARY": "N"},
                {"CONTACT_ID": "11", "SORT": "30", "IS_PRIMARY": "N"},
            ],
            deal_contact_items=[],
        )

        self.assertEqual(
            plan["additions"],
            [
                {"CONTACT_ID": 10, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
                {"CONTACT_ID": 11, "SORT": 30, "ROLE_ID": 0, "IS_PRIMARY": "N"},
            ],
        )

    def test_noops_when_all_company_contacts_are_already_in_deal(self) -> None:
        plan = build_sync_plan(
            deal_id="1",
            company_id="2",
            company_contact_items=[
                {"CONTACT_ID": 10, "SORT": 10, "IS_PRIMARY": "Y"},
            ],
            deal_contact_items=[
                {"CONTACT_ID": 10, "SORT": 10, "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(plan["additions"], [])
        self.assertEqual(plan["additions_count"], 0)
        self.assertEqual(plan["skipped_existing_contact_ids"], ["10"])

    def test_company_id_zero_is_treated_as_missing_company(self) -> None:
        auth = _FakeAuth()

        result = sync_deal_company_contacts(auth, deal_id="204", apply_changes=False)  # type: ignore[arg-type]

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "no_company")
        self.assertEqual(auth.calls, [("crm.deal.get", {"id": "204"})])


if __name__ == "__main__":
    unittest.main()
