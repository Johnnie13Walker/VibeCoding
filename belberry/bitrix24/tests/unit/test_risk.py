import unittest

from belberry.bitrix24.policies import merge_policy as policy
from belberry.bitrix24.policies import risk
from belberry.bitrix24.tests.unit.test_merge_policy import backup_item


class PreflightHighConflictRiskTests(unittest.TestCase):
    def test_low_risk_pair_passes(self):
        target = backup_item("1")
        duplicate = backup_item("2")
        # одинаковые контакты — иначе сработает contact_additions_over_limit
        target["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        duplicate["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "low_risk")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["metrics"]["group_size"], 2)

    def test_group_of_three_blocked(self):
        backup = {
            "target_id": "1",
            "deals": [backup_item("1"), backup_item("2"), backup_item("3")],
        }
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "high_conflict_risk")
        self.assertIn("group_size_gt_max", result["reasons"])

    def test_contact_addition_blocked_at_default_zero(self):
        target = backup_item("1")
        duplicate = backup_item("2")
        target["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        duplicate["contacts"] = [{"CONTACT_ID": "2002", "SORT": 10, "ROLE_ID": 0}]
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertFalse(result["ok"])
        self.assertIn("contact_additions_over_limit", result["reasons"])

    def test_product_signature_blocks_at_default_zero(self):
        target = backup_item("1", product_rows=[{"PRODUCT_NAME": "SEO"}])
        duplicate = backup_item("2", product_rows=[{"PRODUCT_NAME": "SEO"}])
        target["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        duplicate["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertFalse(result["ok"])
        self.assertIn("product_signature_present", result["reasons"])

    def test_activities_total_over_limit(self):
        target = backup_item("1", activities=20)
        duplicate = backup_item("2", activities=20)
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertFalse(result["ok"])
        self.assertIn("activities_total_over_limit", result["reasons"])

    def test_timeline_comments_over_limit(self):
        target = backup_item("1", comments=15)
        duplicate = backup_item("2", comments=15)
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertFalse(result["ok"])
        self.assertIn("timeline_comments_total_over_limit", result["reasons"])

    def test_thresholds_from_config_respected(self):
        target = backup_item("1", activities=20)
        duplicate = backup_item("2", activities=20)
        target["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        duplicate["contacts"] = [{"CONTACT_ID": "1001", "SORT": 10, "ROLE_ID": 0}]
        backup = {"target_id": "1", "deals": [target, duplicate]}
        plan = policy.build_policy_plan(backup, target_id="1")

        permissive = risk.RiskThresholds(max_activities=100)
        result = risk.preflight_high_conflict_risk(backup, plan, thresholds=permissive)

        self.assertTrue(result["ok"])
        self.assertNotIn("activities_total_over_limit", result["reasons"])

    def test_metrics_in_response(self):
        backup = {
            "target_id": "1",
            "deals": [backup_item("1", activities=2, comments=3), backup_item("2", activities=4, comments=5)],
        }
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertEqual(result["metrics"]["activities_total"], 6)
        self.assertEqual(result["metrics"]["timeline_comments_total"], 8)
        self.assertEqual(result["metrics"]["group_size"], 2)

    def test_thresholds_echoed_in_response(self):
        backup = {"target_id": "1", "deals": [backup_item("1"), backup_item("2")]}
        plan = policy.build_policy_plan(backup, target_id="1")

        result = risk.preflight_high_conflict_risk(backup, plan)

        self.assertEqual(result["thresholds"]["max_group_size"], 2)
        self.assertEqual(result["thresholds"]["max_contact_additions"], 0)


if __name__ == "__main__":
    unittest.main()
