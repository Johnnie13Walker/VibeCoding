from __future__ import annotations

from sales_kpi_dashboard import config


def test_sheet_and_tabs_are_configured() -> None:
    assert config.OUTPUT_SHEET_ID == "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"
    assert "Plan" in config.READ_ONLY_TABS
    assert "Plan_MRR" in config.READ_ONLY_TABS
    assert config.WRITEABLE_TABS.isdisjoint(config.READ_ONLY_TABS)


def test_users_are_named() -> None:
    assert all(isinstance(user_id, int) for user_id in config.TM_USERS)
    assert all(" " in name for name in [*config.TM_USERS.values(), *config.MOP_USERS.values()])
