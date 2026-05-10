"""Тесты merge_policy: портированы из legacy test_bitrix_policy_merge_deals.py
плюс дополнительные кейсы на manual_review статусы и authority-логику."""

import unittest

from belberry.bitrix24.policies import merge_policy as policy


def backup_item(deal_id, *, contacts=1, activities=0, comments=0, product_rows=None, company_id="100"):
    return {
        "id": str(deal_id),
        "exists": True,
        "deal": {
            "ID": str(deal_id),
            "TITLE": f"example-{deal_id}.ru",
            "COMPANY_ID": str(company_id),
            "STAGE_ID": "C38:NEW",
            "ASSIGNED_BY_ID": "1",
            "BEGINDATE": "2026-01-01T03:00:00+03:00",
            "CLOSEDATE": "2026-01-08T03:00:00+03:00",
            "OPENED": "N",
            "TYPE_ID": "SALE",
            "CONTACT_ID": str(1000 + int(deal_id)),
            "SOURCE_ID": "1",
            "DATE_CREATE": f"2026-01-{int(deal_id):02d}T09:00:00+03:00",
        },
        "product_rows": product_rows or [],
        "contacts": [{"CONTACT_ID": str(1000 + int(deal_id)), "SORT": 10, "ROLE_ID": 0} for _ in range(contacts)],
        "activities": [{"ID": str(index)} for index in range(activities)],
        "timeline_comments": [{"ID": str(index)} for index in range(comments)],
    }


class BuildPolicyPlanTests(unittest.TestCase):
    def test_low_risk_pair_returns_ready(self):
        target = backup_item("1")
        duplicate = backup_item("2")
        backup = {"target_id": "1", "deals": [target, duplicate]}

        plan = policy.build_policy_plan(backup, target_id="1")

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["target_id"], "1")
        self.assertEqual(plan["earliest_deal_id"], "1")

    def test_invalid_backup_when_target_missing(self):
        backup = {"target_id": "99", "deals": [backup_item("1"), backup_item("2")]}
        plan = policy.build_policy_plan(backup, target_id="99")
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "invalid_backup")

    def test_invalid_backup_when_only_one_deal(self):
        backup = {"target_id": "1", "deals": [backup_item("1")]}
        plan = policy.build_policy_plan(backup, target_id="1")
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "invalid_backup")

    def test_different_companies_returns_manual_review(self):
        backup = {
            "target_id": "1",
            "deals": [backup_item("1", company_id="100"), backup_item("2", company_id="200")],
        }
        plan = policy.build_policy_plan(backup, target_id="1")
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "manual_review_different_companies")
        self.assertEqual(plan["company_ids"], ["100", "200"])

    def test_different_product_signatures_returns_manual_review(self):
        backup = {
            "target_id": "1",
            "deals": [
                backup_item("1", product_rows=[{"PRODUCT_NAME": "SEO"}]),
                backup_item("2", product_rows=[{"PRODUCT_NAME": "SMM"}]),
            ],
        }
        plan = policy.build_policy_plan(backup, target_id="1")
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "manual_review_different_products")

    def test_same_product_signatures_pass(self):
        backup = {
            "target_id": "1",
            "deals": [
                backup_item("1", product_rows=[{"PRODUCT_NAME": "SEO"}]),
                backup_item("2", product_rows=[{"PRODUCT_NAME": "  seo  "}]),
            ],
        }
        plan = policy.build_policy_plan(backup, target_id="1")
        self.assertTrue(plan["ok"])

    def test_attribution_taken_from_earliest(self):
        target = backup_item("2")
        target["deal"]["DATE_CREATE"] = "2026-01-05T09:00:00+03:00"
        target["deal"]["SOURCE_ID"] = "TARGET_SRC"
        target["deal"]["UTM_SOURCE"] = ""
        earliest = backup_item("1")
        earliest["deal"]["DATE_CREATE"] = "2026-01-01T09:00:00+03:00"
        earliest["deal"]["SOURCE_ID"] = "EARLIEST_SRC"
        earliest["deal"]["UTM_SOURCE"] = "google"
        backup = {"target_id": "2", "deals": [earliest, target]}

        plan = policy.build_policy_plan(backup, target_id="2")

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["final_values"]["SOURCE_ID"], "EARLIEST_SRC")
        self.assertEqual(plan["final_values"]["UTM_SOURCE"], "google")

    def test_target_authority_fields_taken_from_target(self):
        target = backup_item("2")
        target["deal"]["STAGE_ID"] = "TARGET_STAGE"
        target["deal"]["ASSIGNED_BY_ID"] = "777"
        earliest = backup_item("1")
        earliest["deal"]["STAGE_ID"] = "EARLIEST_STAGE"
        earliest["deal"]["ASSIGNED_BY_ID"] = "111"
        backup = {"target_id": "2", "deals": [earliest, target]}

        plan = policy.build_policy_plan(backup, target_id="2")

        self.assertEqual(plan["final_values"]["STAGE_ID"], "TARGET_STAGE")
        self.assertEqual(plan["final_values"]["ASSIGNED_BY_ID"], "777")

    def test_lost_reason_filled_from_earliest_non_empty_when_target_empty(self):
        target = backup_item("2")
        target["deal"][policy.LOST_REASON_FIELD] = ""
        first_dup = backup_item("1")
        first_dup["deal"][policy.LOST_REASON_FIELD] = "REASON_FROM_EARLIEST"
        backup = {"target_id": "2", "deals": [first_dup, target]}

        plan = policy.build_policy_plan(backup, target_id="2")

        self.assertEqual(plan["final_values"][policy.LOST_REASON_FIELD], "REASON_FROM_EARLIEST")

    def test_lost_reason_kept_when_target_has_value(self):
        target = backup_item("2")
        target["deal"][policy.LOST_REASON_FIELD] = "TARGET_REASON"
        first_dup = backup_item("1")
        first_dup["deal"][policy.LOST_REASON_FIELD] = "OTHER_REASON"
        backup = {"target_id": "2", "deals": [first_dup, target]}

        plan = policy.build_policy_plan(backup, target_id="2")

        self.assertEqual(plan["final_values"][policy.LOST_REASON_FIELD], "TARGET_REASON")

    def test_contact_additions_unique_only_from_duplicates(self):
        target = backup_item("1")
        target["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        duplicate = backup_item("2")
        duplicate["contacts"] = [
            {"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0},
            {"CONTACT_ID": "2002", "SORT": 20, "ROLE_ID": 0},
        ]
        backup = {"target_id": "1", "deals": [target, duplicate]}

        plan = policy.build_policy_plan(backup, target_id="1")

        ids = [item["CONTACT_ID"] for item in plan["contact_additions"]]
        self.assertEqual(ids, [2002])

    def test_deal_updates_only_for_changed_fields(self):
        target = backup_item("1")
        duplicate = backup_item("2")
        target["deal"]["STAGE_ID"] = "STAGE_X"
        duplicate["deal"]["STAGE_ID"] = "STAGE_Y"
        backup = {"target_id": "1", "deals": [target, duplicate]}

        plan = policy.build_policy_plan(backup, target_id="1")

        ids_with_updates = {item["deal_id"] for item in plan["deal_updates"]}
        self.assertIn("2", ids_with_updates)


if __name__ == "__main__":
    unittest.main()
