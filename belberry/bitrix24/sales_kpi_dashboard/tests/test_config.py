from __future__ import annotations

from sales_kpi_dashboard import config


def test_sheet_and_tabs_are_configured() -> None:
    assert config.OUTPUT_SHEET_ID == "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"
    assert "Plan" in config.READ_ONLY_TABS
    assert "Plan_MRR" in config.READ_ONLY_TABS
    assert "mrr" not in config.WRITEABLE_TABS
    assert config.WRITEABLE_TABS.isdisjoint(config.READ_ONLY_TABS)


def test_products_have_unique_ids() -> None:
    assert len(config.PRODUCTS) == 10
    assert all(isinstance(product_id, int) for product_id in config.PRODUCTS.values())
    assert len(set(config.PRODUCTS.values())) == len(config.PRODUCTS)


def test_role_regexes_match_target_positions_only() -> None:
    assert config.TM_POSITION_REGEX.search("Телемаркетолог")
    assert config.MOP_POSITION_REGEX.search("Менеджер по продажам")
    assert not config.MOP_POSITION_REGEX.search("Аккаунт-менеджер")
