import unittest

from scripts.bitrix_deal_company_enrich_apply import _deal_extra_fields


class DealExtraFieldsTests(unittest.TestCase):
    def test_fills_empty_city_and_client_site(self) -> None:
        fields, notes = _deal_extra_fields(
            {
                "UF_CRM_CITY": "",
                "UF_CRM_SITE": "",
            },
            data={"city": "Москва", "domain": "vegastom.ru", "site": "https://vegastom.ru/"},
            deal_fields_meta={
                "UF_CRM_CITY": {"formLabel": "Город"},
                "UF_CRM_SITE": {"formLabel": "Сайт клиента"},
            },
        )

        self.assertEqual(fields, {"UF_CRM_CITY": "Москва", "UF_CRM_SITE": "vegastom.ru"})
        self.assertEqual([item["status"] for item in notes], ["planned", "planned"])

    def test_does_not_overwrite_existing_values(self) -> None:
        fields, notes = _deal_extra_fields(
            {
                "UF_CRM_CITY": "Москва",
                "UF_CRM_SITE": "vegastom.ru",
            },
            data={"city": "Санкт-Петербург", "domain": "other.ru", "site": "https://other.ru/"},
            deal_fields_meta={
                "UF_CRM_CITY": {"formLabel": "Город"},
                "UF_CRM_SITE": {"formLabel": "Сайт клиента"},
            },
        )

        self.assertEqual(fields, {})
        self.assertEqual([item["status"] for item in notes], ["already_filled", "already_filled"])


if __name__ == "__main__":
    unittest.main()
