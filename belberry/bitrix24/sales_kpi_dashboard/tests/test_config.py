from __future__ import annotations

import importlib
from pathlib import Path

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


def test_mop_regex_includes_sales_rop_but_not_other_rops() -> None:
    r = config.MOP_POSITION_REGEX
    # МОП и РОП-продавец — должны попадать в блок
    assert r.search("Менеджер по продажам")
    assert r.search("менеджер по продажам ")
    assert r.search("Руководитель отдела продаж")
    assert r.search("руководитель отдела ПРОДАЖ")
    assert r.search("РОП")
    assert r.search(" роп ")
    # Соседние роли — не должны
    assert not r.search("Аккаунт-менеджер")
    assert not r.search("Руководитель отдела аккаунтинга")
    assert not r.search("Руководитель отдела ORM и GEO")
    assert not r.search("Руководитель отдела SEO")
    assert not r.search("Административный менеджер")
    assert not r.search("Контент-менеджер")
    assert not r.search("бывший РОП Belberry")


def test_google_sa_key_can_be_overridden_by_env(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_SA_KEY", "/opt/openclaw/secrets/sales-kpi-sa.json")

    reloaded = importlib.reload(config)

    assert reloaded.GOOGLE_SA_KEY == Path("/opt/openclaw/secrets/sales-kpi-sa.json")
    monkeypatch.delenv("GOOGLE_SA_KEY")
    importlib.reload(config)
