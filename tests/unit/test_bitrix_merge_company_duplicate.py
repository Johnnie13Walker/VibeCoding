import unittest

from scripts.bitrix_merge_company_duplicate import _missing_company_contact_links


class CompanyDuplicateMergeTests(unittest.TestCase):
    def test_plans_missing_contacts_only(self) -> None:
        additions = _missing_company_contact_links(
            source_items=[
                {"CONTACT_ID": 10, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
                {"CONTACT_ID": 20, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "N"},
            ],
            target_items=[
                {"CONTACT_ID": 10, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(additions, [{"CONTACT_ID": 20, "SORT": 20, "ROLE_ID": 0, "IS_PRIMARY": "N"}])

    def test_keeps_new_company_primary_unchanged(self) -> None:
        additions = _missing_company_contact_links(
            source_items=[
                {"CONTACT_ID": 30, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
            target_items=[
                {"CONTACT_ID": 40, "SORT": 10, "ROLE_ID": 0, "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(additions[0]["IS_PRIMARY"], "N")


if __name__ == "__main__":
    unittest.main()
