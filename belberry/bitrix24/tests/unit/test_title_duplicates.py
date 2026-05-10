from __future__ import annotations

import unittest

from belberry.bitrix24.tools.title_duplicates import find_title_duplicates, normalize_title


class TitleDuplicatesTests(unittest.TestCase):
    def test_normalize_title_collapses_whitespace_and_lowercases(self) -> None:
        self.assertEqual(normalize_title("  ООО   Ромашка \n test "), "ооо ромашка test")

    def test_empty_input_returns_empty_dict(self) -> None:
        self.assertEqual(find_title_duplicates([]), {})

    def test_single_deal_is_not_duplicate_group(self) -> None:
        self.assertEqual(find_title_duplicates([{"ID": "1", "TITLE": "A"}]), {})

    def test_two_deals_same_title_make_one_group(self) -> None:
        groups = find_title_duplicates([{"ID": "1", "TITLE": "A"}, {"ID": "2", "TITLE": "A"}])

        self.assertEqual(list(groups), ["a"])
        self.assertEqual([deal["ID"] for deal in groups["a"]], ["1", "2"])

    def test_sort_order_by_group_size_then_title(self) -> None:
        groups = find_title_duplicates(
            [
                {"ID": "1", "TITLE": "Beta"},
                {"ID": "2", "TITLE": "Beta"},
                {"ID": "3", "TITLE": "Alpha"},
                {"ID": "4", "TITLE": "Alpha"},
                {"ID": "5", "TITLE": "Alpha"},
                {"ID": "6", "TITLE": "Gamma"},
                {"ID": "7", "TITLE": "Gamma"},
            ]
        )

        self.assertEqual(list(groups), ["alpha", "beta", "gamma"])

    def test_case_insensitive_matching(self) -> None:
        groups = find_title_duplicates([{"ID": "1", "TITLE": "Clinic"}, {"ID": "2", "TITLE": "clinic"}])

        self.assertEqual(list(groups), ["clinic"])

    def test_whitespace_normalization_matching(self) -> None:
        groups = find_title_duplicates([{"ID": "1", "TITLE": "A  B"}, {"ID": "2", "TITLE": " A B "}])

        self.assertEqual(list(groups), ["a b"])

    def test_sorting_inside_group_by_date_create_then_id(self) -> None:
        groups = find_title_duplicates(
            [
                {"ID": "3", "TITLE": "A", "DATE_CREATE": "2026-05-02"},
                {"ID": "2", "TITLE": "A", "DATE_CREATE": "2026-05-01"},
                {"ID": "1", "TITLE": "A", "DATE_CREATE": "2026-05-01"},
            ]
        )

        self.assertEqual([deal["ID"] for deal in groups["a"]], ["1", "2", "3"])

    def test_empty_titles_are_skipped(self) -> None:
        groups = find_title_duplicates([{"ID": "1", "TITLE": ""}, {"ID": "2"}, {"ID": "3", "TITLE": "A"}])

        self.assertEqual(groups, {})


if __name__ == "__main__":
    unittest.main()
