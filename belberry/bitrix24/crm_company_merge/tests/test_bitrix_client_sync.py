from __future__ import annotations

import os
from pathlib import Path

import pytest

from crm_company_merge.bitrix_client import SYNC_SCRIPT


@pytest.mark.skipif(
    not Path("/opt/openclaw/repos/vibecoding").exists(),
    reason="VPS-only check: sync script lives under /opt/openclaw/repos/vibecoding",
)
def test_sync_script_resolves_to_existing_file() -> None:
    assert SYNC_SCRIPT.exists()
    assert SYNC_SCRIPT.is_file()
    assert os.access(SYNC_SCRIPT, os.X_OK)
