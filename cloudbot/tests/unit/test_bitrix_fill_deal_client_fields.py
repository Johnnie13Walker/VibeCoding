import unittest

from scripts.bitrix_fill_deal_client_fields import _clean_domain, _clean_site_url, _plan_field_update


class DealClientFieldsPlanTests(unittest.TestCase):
    def test_selects_primary_empty_client_site_field(self) -> None:
        updates, note = _plan_field_update(
            {
                "UF_CRM_1776434217": "",
                "UF_CRM_69E8AB2E0715A": "",
            },
            {
                "UF_CRM_1776434217": {"formLabel": "Сайт клиента"},
                "UF_CRM_69E8AB2E0715A": {"formLabel": "Сайт клиента"},
            },
            field_kind="client_site",
            field_codes=["UF_CRM_1776434217", "UF_CRM_69E8AB2E0715A"],
            target_value="https://koleno.su/",
            overwrite=False,
        )

        self.assertEqual(updates, {"UF_CRM_1776434217": "https://koleno.su/"})
        self.assertEqual(note["status"], "planned")

    def test_does_not_overwrite_alternative_client_site_field(self) -> None:
        updates, note = _plan_field_update(
            {
                "UF_CRM_1776434217": "",
                "UF_CRM_69E8AB2E0715A": "https://koleno.su/",
            },
            {
                "UF_CRM_1776434217": {"formLabel": "Сайт клиента"},
                "UF_CRM_69E8AB2E0715A": {"formLabel": "Сайт клиента"},
            },
            field_kind="client_site",
            field_codes=["UF_CRM_1776434217", "UF_CRM_69E8AB2E0715A"],
            target_value="https://other.ru/",
            overwrite=False,
        )

        self.assertEqual(updates, {})
        self.assertEqual(note["status"], "already_filled")

    def test_does_not_overwrite_filled_city(self) -> None:
        updates, note = _plan_field_update(
            {"UF_CRM_5FB3854A1EDBC": "Москва"},
            {"UF_CRM_5FB3854A1EDBC": {"formLabel": "Город"}},
            field_kind="city",
            field_codes=["UF_CRM_5FB3854A1EDBC"],
            target_value="Санкт-Петербург",
            overwrite=False,
        )

        self.assertEqual(updates, {})
        self.assertEqual(note["status"], "already_filled")

    def test_cleans_site_url_and_domain(self) -> None:
        self.assertEqual(_clean_site_url("https://l-v-c.ru/#rec661876504"), "https://l-v-c.ru")
        self.assertEqual(_clean_domain("https://www.l-v-c.ru/path?a=1#b"), "l-v-c.ru")


if __name__ == "__main__":
    unittest.main()
