import json
import tempfile
import unittest
from pathlib import Path

from belberry.bitrix24.orchestration import ledger
from belberry.bitrix24.policies.operation_key import POLICY_VERSION, build_operation_key


def make_record(*, status="apply_started", sheet_status="not_ready", run_id="r1", **overrides):
    op_key = build_operation_key(
        sheet_id="s1",
        domain="example.ru",
        target_id="20",
        deal_ids=["10", "20"],
    )
    base = dict(
        operation_key=op_key,
        sheet_id="s1",
        domain="example.ru",
        target_id="20",
        deal_ids=("20", "10"),
        policy_version=POLICY_VERSION,
        status=status,
        crm_status="started",
        sheet_status=sheet_status,
        run_id=run_id,
        dry_run_artifact="outputs/runs/r1/dry_run_plan.json",
        crm_backup_path="outputs/runs/r1/crm_backup.json",
    )
    base.update(overrides)
    return ledger.MergeLedgerRecord(**base)


class ClassifyResultTests(unittest.TestCase):
    def test_applied_result_pending_archive(self):
        status, crm_status, sheet_status = ledger.classify_result({"ok": True, "status": "applied"})
        self.assertEqual(status, "crm_applied_sheet_pending")
        self.assertEqual(crm_status, "applied")
        self.assertEqual(sheet_status, "pending_archive")

    def test_manual_review_pending_mark(self):
        status, crm_status, sheet_status = ledger.classify_result(
            {"ok": False, "status": "manual_review_high_conflict_risk"}
        )
        self.assertEqual(status, "manual_review_sheet_pending")
        self.assertEqual(sheet_status, "pending_manual_review_mark")

    def test_merge_conflict_pending_mark(self):
        status, _, sheet_status = ledger.classify_result(
            {"ok": False, "status": "merge_not_success_after_policy"}
        )
        self.assertEqual(status, "merge_conflict_sheet_pending")
        self.assertEqual(sheet_status, "pending_conflict_mark")

    def test_none_result_means_unknown_needs_reconcile(self):
        status, crm_status, sheet_status = ledger.classify_result(None)
        self.assertEqual(status, "apply_unknown_needs_reconcile")
        self.assertEqual(crm_status, "unknown_after_apply")
        self.assertEqual(sheet_status, "not_ready")


class AppendAndReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "nested" / "ledger.jsonl"

    def test_append_creates_parent_dir(self):
        ledger.append_record(self.path, make_record())
        self.assertTrue(self.path.exists())

    def test_append_writes_jsonl_line(self):
        record = make_record()
        ledger.append_record(self.path, record)
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["operation_key"], record.operation_key)
        self.assertEqual(parsed["deal_ids"], list(record.deal_ids))

    def test_iter_records_handles_missing_file(self):
        self.assertEqual(list(ledger.iter_records(self.path)), [])

    def test_iter_records_skips_invalid_lines(self):
        ledger.append_record(self.path, make_record())
        with self.path.open("a", encoding="utf-8") as h:
            h.write("not json\n")
        ledger.append_record(self.path, make_record(status="crm_applied_sheet_pending"))
        records = list(ledger.iter_records(self.path))
        self.assertEqual(len(records), 2)


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.jsonl"
        self.op_key = build_operation_key(
            sheet_id="s1",
            domain="example.ru",
            target_id="20",
            deal_ids=["10", "20"],
        )

    def test_latest_by_operation_key_picks_last(self):
        ledger.append_record(self.path, make_record(status="apply_started"))
        ledger.append_record(self.path, make_record(status="crm_applied_sheet_pending"))
        latest = ledger.latest_by_operation_key(self.path)
        self.assertEqual(latest[self.op_key]["status"], "crm_applied_sheet_pending")

    def test_is_operation_already_applied_false_for_unknown_key(self):
        self.assertFalse(ledger.is_operation_already_applied(self.path, "no-such-key"))

    def test_is_operation_already_applied_false_for_apply_started(self):
        ledger.append_record(self.path, make_record(status="apply_started"))
        self.assertFalse(ledger.is_operation_already_applied(self.path, self.op_key))

    def test_is_operation_already_applied_true_for_crm_applied(self):
        ledger.append_record(self.path, make_record(status="crm_applied_sheet_pending"))
        self.assertTrue(ledger.is_operation_already_applied(self.path, self.op_key))

    def test_is_operation_already_applied_true_for_archived(self):
        ledger.append_record(self.path, make_record(status="crm_applied_sheet_archived"))
        self.assertTrue(ledger.is_operation_already_applied(self.path, self.op_key))

    def test_is_operation_locked_for_retry_includes_unknown(self):
        ledger.append_record(self.path, make_record(status="apply_unknown_needs_reconcile"))
        self.assertTrue(ledger.is_operation_locked_for_retry(self.path, self.op_key))
        self.assertFalse(ledger.is_operation_already_applied(self.path, self.op_key))

    def test_transition_appends_new_line_with_same_key(self):
        ledger.append_record(self.path, make_record(status="apply_started"))
        ledger.transition(
            self.path,
            self.op_key,
            status="crm_applied_sheet_pending",
            sheet_status="pending_archive",
            crm_status="applied",
            note="merge SUCCESS",
        )
        records = list(ledger.iter_records(self.path))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["status"], "crm_applied_sheet_pending")
        self.assertEqual(records[1]["sheet_status"], "pending_archive")
        self.assertEqual(records[1]["note"], "merge SUCCESS")

    def test_transition_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            ledger.transition(self.path, "no-such-key", status="x")

    def test_two_phase_sheet_sync_transition_chain(self):
        ledger.append_record(self.path, make_record(status="apply_started"))
        ledger.transition(self.path, self.op_key, status="crm_applied_sheet_pending", sheet_status="pending_archive")
        ledger.transition(self.path, self.op_key, status="crm_applied_archive_appended", sheet_status="appended_pending_delete")
        ledger.transition(self.path, self.op_key, status="crm_applied_sheet_archived", sheet_status="archived")
        latest = ledger.find_latest(self.path, self.op_key)
        self.assertEqual(latest["status"], "crm_applied_sheet_archived")
        self.assertEqual(latest["sheet_status"], "archived")
        self.assertTrue(ledger.is_operation_already_applied(self.path, self.op_key))


class SummarizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.jsonl"

    def test_summarize_counts_by_latest_status(self):
        ledger.append_record(self.path, make_record(operation_key="k1", status="crm_applied_sheet_pending"))
        ledger.append_record(self.path, make_record(operation_key="k2", status="manual_review_sheet_pending"))
        summary = ledger.summarize(self.path)
        self.assertEqual(summary["crm_applied_sheet_pending"], 1)
        self.assertEqual(summary["manual_review_sheet_pending"], 1)

    def test_summarize_uses_latest_status_per_key(self):
        ledger.append_record(self.path, make_record(operation_key="k1", status="apply_started"))
        ledger.append_record(self.path, make_record(operation_key="k1", status="crm_applied_sheet_archived"))
        summary = ledger.summarize(self.path)
        self.assertEqual(summary, {"crm_applied_sheet_archived": 1})


if __name__ == "__main__":
    unittest.main()
