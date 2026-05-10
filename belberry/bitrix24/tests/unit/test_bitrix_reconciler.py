from __future__ import annotations

import unittest
from typing import Any, Mapping

from belberry.bitrix24.orchestration.dry_run import backup_fingerprint
from belberry.bitrix24.policies.merge_policy import build_policy_plan
from belberry.bitrix24.providers.bitrix_oauth import BitrixOAuthError
from belberry.bitrix24.providers.bitrix_reconciler import (
    ACTIVITY_SELECT_DEFAULT,
    ReconcileSettings,
    crm_methods_used,
    live_reconcile,
)


class FakeBitrix:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []
        self.fail_methods: dict[str, Exception] = {}
        self.deals = {
            "10": {
                "ID": "10",
                "TITLE": "Целевая",
                "CATEGORY_ID": "7",
                "STAGE_ID": "C7:NEW",
                "SOURCE_ID": "CALL",
                "ASSIGNED_BY_ID": "100",
                "COMPANY_ID": "300",
                "CONTACT_ID": "500",
                "DATE_CREATE": "2026-05-01T10:00:00+03:00",
                "DATE_MODIFY": "2026-05-02T10:00:00+03:00",
                "BEGINDATE": "2026-05-01",
                "CLOSEDATE": "2026-05-30",
                "OPENED": "Y",
                "TYPE_ID": "SALE",
            },
            "20": {
                "ID": "20",
                "TITLE": "Дубль",
                "CATEGORY_ID": "7",
                "STAGE_ID": "C7:NEW",
                "SOURCE_ID": "CALL",
                "ASSIGNED_BY_ID": "100",
                "COMPANY_ID": "300",
                "CONTACT_ID": "501",
                "DATE_CREATE": "2026-05-03T10:00:00+03:00",
                "DATE_MODIFY": "2026-05-04T10:00:00+03:00",
                "BEGINDATE": "2026-05-03",
                "CLOSEDATE": "2026-05-30",
                "OPENED": "Y",
                "TYPE_ID": "SALE",
            },
        }
        self.product_rows = {"10": [], "20": []}
        self.contacts = {
            "10": [{"CONTACT_ID": "500", "SORT": "10", "ROLE_ID": "0"}],
            "20": [{"CONTACT_ID": "500", "SORT": "10", "ROLE_ID": "0"}],
        }
        self.activities = {
            "10": [{"ID": "a1", "OWNER_ID": "10", "SUBJECT": "first"}],
            "20": [{"ID": "a2", "OWNER_ID": "20", "SUBJECT": "second"}],
        }
        self.timeline = {"10": [{"ID": "t1"}], "20": []}

    def _maybe_fail(self, method: str) -> None:
        if method in self.fail_methods:
            raise self.fail_methods[method]

    def call_method(self, method: str, params: Mapping[str, Any] | None = None, *, default: Any = None) -> Any:
        self.calls.append(("call_method", method, params))
        self._maybe_fail(method)
        params = dict(params or {})
        if method == "crm.deal.get":
            return self.deals.get(str(params.get("id")), default)
        if method == "crm.deal.productrows.get":
            return self.product_rows.get(str(params.get("id")), [])
        if method == "crm.deal.contact.items.get":
            return self.contacts.get(str(params.get("id")), [])
        if method == "crm.timeline.comment.list":
            deal_id = str(params.get("filter", {}).get("ENTITY_ID"))
            return self.timeline.get(deal_id, [])
        if method == "crm.status.list":
            entity_id = params.get("filter", {}).get("ENTITY_ID")
            if entity_id == "SOURCE":
                return [{"STATUS_ID": "CALL", "NAME": "Звонок"}]
            if entity_id == "DEAL_STAGE_7":
                return [{"STATUS_ID": "C7:NEW", "NAME": "Новая"}]
            if entity_id == "DEAL_STAGE":
                return [{"STATUS_ID": "NEW", "NAME": "Новая"}]
            return []
        raise AssertionError(f"unexpected call_method {method}")

    def call_payload(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("call_payload", method, params))
        self._maybe_fail(method)
        if method == "crm.category.list":
            return {"result": {"categories": [{"id": "7", "name": "Реанимация"}]}}
        raise AssertionError(f"unexpected call_payload {method}")

    def list_method(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(("list_method", method, params))
        self._maybe_fail(method)
        if method == "crm.activity.list":
            deal_id = str((params or {}).get("filter", {}).get("OWNER_ID"))
            return self.activities.get(deal_id, [])
        raise AssertionError(f"unexpected list_method {method}")


class BitrixReconcilerTests(unittest.TestCase):
    def settings(self) -> ReconcileSettings:
        return ReconcileSettings(portal_base_url="https://portal.example")

    def test_crm_methods_used_are_read_only(self) -> None:
        methods = crm_methods_used()

        self.assertEqual(
            methods,
            (
                "crm.deal.get",
                "crm.deal.productrows.get",
                "crm.deal.contact.items.get",
                "crm.activity.list",
                "crm.timeline.comment.list",
                "crm.category.list",
                "crm.status.list",
            ),
        )
        forbidden = ("update", "delete", "merge", "add", "set")
        self.assertFalse([method for method in methods if any(word in method.lower() for word in forbidden)])

    def test_live_reconcile_builds_policy_and_fingerprint_compatible_backup(self) -> None:
        fake = FakeBitrix()

        backup = live_reconcile(oauth=fake, deal_ids=["20", "10"], target_id="10", settings=self.settings())
        plan = build_policy_plan(backup, target_id="10")
        fingerprint = backup_fingerprint(backup)

        self.assertEqual(backup["target_id"], "10")
        self.assertEqual(backup["entity_ids_for_merge"], ["10", "20"])
        self.assertEqual([item["id"] for item in backup["deals"]], ["10", "20"])
        self.assertTrue(all(item["exists"] for item in backup["deals"]))
        self.assertEqual(backup["summaries"][0]["url"], "https://portal.example/crm/deal/details/10/")
        self.assertEqual(backup["summaries"][0]["category_name"], "Реанимация")
        self.assertEqual(backup["summaries"][0]["stage_name"], "Новая")
        self.assertEqual(backup["summaries"][0]["source_name"], "Звонок")
        self.assertTrue(plan["ok"])
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

    def test_live_reconcile_uses_custom_activity_select(self) -> None:
        fake = FakeBitrix()
        settings = ReconcileSettings(portal_base_url="https://portal.example", activity_select=("ID", "SUBJECT"))

        live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=settings)

        activity_calls = [params for kind, method, params in fake.calls if method == "crm.activity.list"]
        self.assertEqual(activity_calls[0]["select"], ("ID", "SUBJECT"))

    def test_default_activity_select_is_contract_constant(self) -> None:
        self.assertIn("COMMUNICATIONS", ACTIVITY_SELECT_DEFAULT)
        self.assertIn("SETTINGS", ACTIVITY_SELECT_DEFAULT)

    def test_missing_deal_is_marked_without_child_reads(self) -> None:
        fake = FakeBitrix()
        backup = live_reconcile(oauth=fake, deal_ids=["20", "99"], target_id="20", settings=self.settings())

        missing = backup["deals"][1]

        self.assertEqual(missing, {"id": "99", "exists": False, "deal": {}})
        methods_for_missing = [method for _, method, params in fake.calls if params and params.get("id") == "99"]
        self.assertEqual(methods_for_missing, ["crm.deal.get"])

    def test_deal_get_error_is_captured_as_missing_error_payload(self) -> None:
        fake = FakeBitrix()
        fake.fail_methods["crm.deal.get"] = BitrixOAuthError("denied", code="ACCESS_DENIED", category="access_denied")

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        self.assertFalse(backup["deals"][0]["exists"])
        self.assertEqual(backup["deals"][0]["error"]["status"], "access denied")

    def test_child_read_errors_are_embedded_in_list_fields(self) -> None:
        fake = FakeBitrix()
        fake.fail_methods["crm.activity.list"] = BitrixOAuthError("rate", code="QUERY_LIMIT_EXCEEDED")

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        self.assertEqual(backup["deals"][0]["activities"][0]["__error__"]["code"], "QUERY_LIMIT_EXCEEDED")

    def test_category_and_status_errors_fall_back_to_ids(self) -> None:
        fake = FakeBitrix()
        fake.fail_methods["crm.category.list"] = BitrixOAuthError("bad")
        fake.fail_methods["crm.status.list"] = BitrixOAuthError("bad")

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        self.assertEqual(backup["summaries"][0]["category_name"], "7")
        self.assertEqual(backup["summaries"][0]["stage_name"], "C7:NEW")
        self.assertEqual(backup["summaries"][0]["source_name"], "CALL")

    def test_malformed_category_payload_is_ignored(self) -> None:
        class BadCategoryPayload(FakeBitrix):
            def call_payload(self, method, params=None, *, default=None):
                self.calls.append(("call_payload", method, params))
                if method == "crm.category.list":
                    return {"result": {"categories": ["bad", {"id": "", "name": "empty"}]}}
                return super().call_payload(method, params, default=default)

        backup = live_reconcile(
            oauth=BadCategoryPayload(),
            deal_ids=["10", "20"],
            target_id="10",
            settings=self.settings(),
        )

        self.assertEqual(backup["summaries"][0]["category_name"], "7")

    def test_non_list_category_payload_is_ignored(self) -> None:
        class NonListCategoryPayload(FakeBitrix):
            def call_payload(self, method, params=None, *, default=None):
                self.calls.append(("call_payload", method, params))
                if method == "crm.category.list":
                    return {"result": {"categories": {"id": "7"}}}
                return super().call_payload(method, params, default=default)

        backup = live_reconcile(
            oauth=NonListCategoryPayload(),
            deal_ids=["10", "20"],
            target_id="10",
            settings=self.settings(),
        )

        self.assertEqual(backup["summaries"][0]["category_name"], "7")

    def test_non_list_child_payloads_become_empty_lists(self) -> None:
        fake = FakeBitrix()
        fake.contacts["10"] = "bad"  # type: ignore[assignment]

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        self.assertEqual(backup["deals"][0]["contacts"], [])

    def test_generic_child_exception_is_embedded_as_error_payload(self) -> None:
        fake = FakeBitrix()
        fake.fail_methods["crm.timeline.comment.list"] = RuntimeError("plain failure")

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        self.assertEqual(backup["deals"][0]["timeline_comments"][0]["__error__"]["message"], "plain failure")

    def test_invalid_ids_raise_before_reading_crm(self) -> None:
        fake = FakeBitrix()

        with self.assertRaisesRegex(ValueError, "target_id"):
            live_reconcile(oauth=fake, deal_ids=["10"], target_id="abc", settings=self.settings())

        with self.assertRaisesRegex(ValueError, "deal_ids"):
            live_reconcile(oauth=fake, deal_ids=["10"], target_id="10", settings=self.settings())

        self.assertEqual(fake.calls, [])

    def test_portal_base_url_is_not_hardcoded(self) -> None:
        fake = FakeBitrix()
        settings = ReconcileSettings(portal_base_url="https://custom.example/")

        backup = live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=settings)

        self.assertEqual(backup["summaries"][0]["url"], "https://custom.example/crm/deal/details/10/")

    def test_methods_called_match_declaration(self) -> None:
        fake = FakeBitrix()

        live_reconcile(oauth=fake, deal_ids=["10", "20"], target_id="10", settings=self.settings())

        called = {method for _, method, _ in fake.calls}
        self.assertTrue(called.issubset(set(crm_methods_used())))


if __name__ == "__main__":
    unittest.main()
