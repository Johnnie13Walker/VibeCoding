import unittest

from scripts.bitrix_link_deal_existing_company import _deal_contact_company_additions


class LinkDealExistingCompanyTests(unittest.TestCase):
    def test_adds_deal_contacts_missing_from_company(self) -> None:
        additions = _deal_contact_company_additions(
            deal_contact_items=[
                {"CONTACT_ID": 10, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
                {"CONTACT_ID": 20, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "N"},
            ],
            company_contact_items=[
                {"CONTACT_ID": 10, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(additions, [{"CONTACT_ID": 20, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "N"}])

    def test_keeps_existing_company_primary(self) -> None:
        additions = _deal_contact_company_additions(
            deal_contact_items=[
                {"CONTACT_ID": 30, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
            company_contact_items=[
                {"CONTACT_ID": 40, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(additions[0]["IS_PRIMARY"], "N")


if __name__ == "__main__":
    unittest.main()
