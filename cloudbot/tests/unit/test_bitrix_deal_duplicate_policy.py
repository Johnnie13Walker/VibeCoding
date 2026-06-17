from __future__ import annotations

import unittest

from cloudbot.providers.bitrix.deal_duplicate_policy import (
    group_deals_by_domain,
    plan_duplicate_group,
)


class BitrixDealDuplicatePolicyTests(unittest.TestCase):
    def test_success_deal_becomes_target_and_attribution_comes_from_earliest_deal(self) -> None:
        plan = plan_duplicate_group(
            [
                {
                    "id": "101",
                    "title": "acme.ru / первичный контакт",
                    "category_name": "Телемаркетинг",
                    "stage_name": "К обзвону",
                    "created_at": "2026-01-10T09:00:00+03:00",
                    "updated_at": "2026-01-11T09:00:00+03:00",
                    "SOURCE_ID": "SEO",
                    "UTM_SOURCE": "yandex",
                },
                {
                    "id": "202",
                    "title": "acme.ru / SEO",
                    "category_name": "Продажи",
                    "stage_name": "УСПЕХ",
                    "created_at": "2026-02-10T09:00:00+03:00",
                    "updated_at": "2026-02-12T09:00:00+03:00",
                    "SOURCE_ID": "CALL",
                },
            ],
            domain_key="acme.ru",
        )

        self.assertEqual(len(plan.actions), 1)
        action = plan.actions[0]
        self.assertEqual(action.target_id, "202")
        self.assertEqual(action.duplicate_ids, ("101",))
        self.assertEqual(action.attribution_source_id, "101")
        self.assertEqual(action.attribution_updates["SOURCE_ID"], "SEO")
        self.assertEqual(action.attribution_updates["UTM_SOURCE"], "yandex")

    def test_multiple_success_deals_with_different_products_are_not_merged_together(self) -> None:
        deals = [
            {
                "id": "301",
                "title": "brand.ru / SEO",
                "category_name": "Продажи",
                "stage_name": "УСПЕХ",
                "created_at": "2026-01-10T09:00:00+03:00",
                "updated_at": "2026-01-11T09:00:00+03:00",
            },
            {
                "id": "302",
                "title": "brand.ru / AEO",
                "category_name": "Продажи",
                "stage_name": "УСПЕХ",
                "created_at": "2026-01-12T09:00:00+03:00",
                "updated_at": "2026-01-13T09:00:00+03:00",
            },
            {
                "id": "303",
                "title": "brand.ru / SEO дубль",
                "category_name": "Телемаркетинг",
                "stage_name": "Взято в работу",
                "created_at": "2026-01-09T09:00:00+03:00",
                "updated_at": "2026-01-14T09:00:00+03:00",
            },
        ]

        plan = plan_duplicate_group(
            deals,
            domain_key="brand.ru",
            product_rows_by_deal={
                "301": [{"PRODUCT_NAME": "SEO"}],
                "302": [{"PRODUCT_NAME": "AEO"}],
                "303": [{"PRODUCT_NAME": "SEO"}],
            },
        )

        self.assertEqual(len(plan.actions), 1)
        self.assertEqual(plan.actions[0].target_id, "301")
        self.assertEqual(plan.actions[0].duplicate_ids, ("303",))
        self.assertEqual(plan.skipped_ids, ())
        self.assertNotIn("302", plan.actions[0].duplicate_ids)

    def test_accounting_deal_is_protected_and_sales_deal_stays_primary(self) -> None:
        plan = plan_duplicate_group(
            [
                {
                    "id": "401",
                    "title": "client.ru",
                    "category_name": "Аккаунтинг NEW",
                    "stage_name": "Передача клиента",
                    "created_at": "2026-01-01T09:00:00+03:00",
                    "updated_at": "2026-01-02T09:00:00+03:00",
                },
                {
                    "id": "402",
                    "title": "client.ru / продажа",
                    "category_name": "Продажи",
                    "stage_name": "Подготовка КП",
                    "created_at": "2026-02-01T09:00:00+03:00",
                    "updated_at": "2026-02-03T09:00:00+03:00",
                },
                {
                    "id": "403",
                    "title": "client.ru / обзвон",
                    "category_name": "Телемаркетинг",
                    "stage_name": "Взято в работу",
                    "created_at": "2026-01-15T09:00:00+03:00",
                    "updated_at": "2026-02-04T09:00:00+03:00",
                },
            ],
            domain_key="client.ru",
        )

        self.assertEqual(plan.protected_ids, ("401",))
        self.assertEqual(len(plan.actions), 1)
        self.assertEqual(plan.actions[0].target_id, "402")
        self.assertEqual(plan.actions[0].duplicate_ids, ("403",))

    def test_telemarketing_only_group_uses_freshest_deal_as_target(self) -> None:
        plan = plan_duplicate_group(
            [
                {
                    "id": "501",
                    "title": "tm-only.ru",
                    "category_name": "Телемаркетинг",
                    "stage_name": "К обзвону",
                    "created_at": "2026-01-01T09:00:00+03:00",
                    "updated_at": "2026-01-02T09:00:00+03:00",
                },
                {
                    "id": "502",
                    "title": "tm-only.ru",
                    "category_name": "Телемаркетинг",
                    "stage_name": "Взято в работу",
                    "created_at": "2026-01-03T09:00:00+03:00",
                    "updated_at": "2026-01-05T09:00:00+03:00",
                },
            ],
            domain_key="tm-only.ru",
        )

        self.assertEqual(plan.actions[0].target_id, "502")
        self.assertEqual(plan.actions[0].duplicate_ids, ("501",))

    def test_domain_grouping_uses_explicit_domain_before_title(self) -> None:
        groups = group_deals_by_domain(
            [
                {"id": "601", "domain": "https://www.example.ru/path", "title": "без домена"},
                {"id": "602", "domain": "example.ru", "title": "другая сделка"},
                {"id": "603", "title": "solo.ru"},
            ]
        )

        self.assertEqual([item["id"] for item in groups["example.ru"]], ["601", "602"])
        self.assertNotIn("solo.ru", groups)

    def test_domain_grouping_ignores_date_like_titles(self) -> None:
        groups = group_deals_by_domain(
            [
                {"id": "701", "title": "Кристина, вход 01.09"},
                {"id": "702", "title": "01.09 повторный вход"},
                {"id": "703", "title": "real-client.ru"},
                {"id": "704", "title": "https://real-client.ru/brief"},
            ]
        )

        self.assertNotIn("01.09", groups)
        self.assertEqual([item["id"] for item in groups["real-client.ru"]], ["703", "704"])


if __name__ == "__main__":
    unittest.main()
