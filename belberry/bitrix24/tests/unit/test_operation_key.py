import unittest

from belberry.bitrix24.policies import operation_key as op


class OperationKeyTests(unittest.TestCase):
    base_kwargs = dict(
        sheet_id="1abcXYZ",
        domain="example.ru",
        target_id="20",
        deal_ids=["10", "20", "30"],
    )

    def test_key_is_stable_for_same_inputs(self):
        first = op.build_operation_key(**self.base_kwargs)
        second = op.build_operation_key(**self.base_kwargs)
        self.assertEqual(first, second)

    def test_target_first_then_others_ascending(self):
        key = op.build_operation_key(**self.base_kwargs)
        self.assertIn("|target=20|ids=20,10,30|", key)

    def test_key_changes_when_policy_version_changes(self):
        a = op.build_operation_key(**self.base_kwargs, policy_version="v1")
        b = op.build_operation_key(**self.base_kwargs, policy_version="v2")
        self.assertNotEqual(a, b)

    def test_key_changes_when_sheet_id_changes(self):
        a = op.build_operation_key(**self.base_kwargs)
        b = op.build_operation_key(**{**self.base_kwargs, "sheet_id": "OTHER"})
        self.assertNotEqual(a, b)

    def test_domain_normalization(self):
        a = op.build_operation_key(**self.base_kwargs)
        b = op.build_operation_key(**{**self.base_kwargs, "domain": "HTTPS://WWW.Example.RU/"})
        self.assertEqual(a, b)

    def test_non_numeric_ids_dropped(self):
        kwargs = {**self.base_kwargs, "deal_ids": ["10", "20", "abc", "", None, "30"]}
        key = op.build_operation_key(**kwargs)
        self.assertIn("|ids=20,10,30|", key)

    def test_target_must_be_in_ids(self):
        with self.assertRaises(ValueError):
            op.build_operation_key(
                sheet_id="s",
                domain="example.ru",
                target_id="99",
                deal_ids=["10", "20"],
            )

    def test_at_least_two_ids_required(self):
        with self.assertRaises(ValueError):
            op.build_operation_key(
                sheet_id="s",
                domain="example.ru",
                target_id="20",
                deal_ids=["20"],
            )

    def test_sheet_id_required(self):
        with self.assertRaises(ValueError):
            op.build_operation_key(
                sheet_id="",
                domain="example.ru",
                target_id="20",
                deal_ids=["10", "20"],
            )

    def test_target_id_must_be_numeric(self):
        with self.assertRaises(ValueError):
            op.build_operation_key(
                sheet_id="s",
                domain="example.ru",
                target_id="abc",
                deal_ids=["10", "20"],
            )

    def test_policy_version_constant_present(self):
        self.assertTrue(op.POLICY_VERSION)
        self.assertRegex(op.POLICY_VERSION, r"^\d{4}\.\d{2}\.\d{2}$")


if __name__ == "__main__":
    unittest.main()
