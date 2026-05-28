from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_PATH = (
    ROOT_DIR
    / "server_snapshots/live_ams_1_vm_76ds_20260325/opt/openclaw/local/bitrix_app_server.py"
)


def _load_server_module():
    spec = importlib.util.spec_from_file_location("bitrix_app_server_for_test", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Не удалось загрузить bitrix_app_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BitrixAppServerSyncContactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _load_server_module()

    def test_extracts_company_id_from_bizproc_properties(self) -> None:
        request = self.server._extract_sync_request(
            {
                "properties[companyId]": "56686",
                "properties[syncClosedDeals]": "Y",
                "properties[maxDeals]": "25",
            }
        )

        self.assertEqual(request["company_id"], "56686")
        self.assertEqual(request["deal_id"], "")
        self.assertTrue(request["include_closed"])
        self.assertEqual(request["max_deals"], 25)

    def test_extracts_company_id_from_document_id_when_property_absent(self) -> None:
        request = self.server._extract_sync_request(
            {
                "document_id": ["crm", "CCrmDocumentCompany", "COMPANY_1516"],
                "properties[syncClosedDeals]": "N",
            }
        )

        self.assertEqual(request["company_id"], "1516")
        self.assertFalse(request["include_closed"])

    def test_builds_add_only_plan_for_server_endpoint(self) -> None:
        plan = self.server._build_sync_plan(
            deal_id="23512",
            company_id="56686",
            company_contact_items=[
                {"CONTACT_ID": "70334", "SORT": "10"},
                {"CONTACT_ID": "70472", "SORT": "30"},
            ],
            deal_contact_items=[
                {"CONTACT_ID": "70334", "SORT": "10", "IS_PRIMARY": "Y"},
            ],
        )

        self.assertEqual(plan["skipped_existing_contact_ids"], ["70334"])
        self.assertEqual(
            plan["additions"],
            [{"CONTACT_ID": 70472, "SORT": 30, "ROLE_ID": 0, "IS_PRIMARY": "N"}],
        )


if __name__ == "__main__":
    unittest.main()
