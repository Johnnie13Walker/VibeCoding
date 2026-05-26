"""Unit-тесты ключевой логики скоринга — компании, фильтра и сводки."""

import unittest

from empty_companies_score.config import UF_BRAND, UF_CITY, UF_REVENUE, UF_SITE
from empty_companies_score.scorer import (
    score_companies,
    select_for_upload,
    summary_counts,
)


def _company(cid: str, **fields) -> dict:
    base = {
        "ID": cid,
        "TITLE": f"Company {cid}",
        "DATE_CREATE": "2020-01-01T00:00:00",
        "DATE_MODIFY": "2020-01-02T00:00:00",
        "ASSIGNED_BY_ID": "1",
        "CREATED_BY_ID": "1",
        UF_BRAND: "",
        UF_CITY: "",
        UF_SITE: "",
        UF_REVENUE: "",
    }
    base.update(fields)
    return base


class ScorerTests(unittest.TestCase):
    def test_full_empty_company_scores_3_and_safe(self):
        companies = [_company("100")]
        scored = score_companies(companies, [], [], [], [], {"1": "Иван"})
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0].score, 3)
        self.assertTrue(scored[0].safe_to_delete)
        self.assertTrue(scored[0].empty_links)
        self.assertTrue(scored[0].empty_inn)
        self.assertTrue(scored[0].empty_uf)

    def test_one_uf_filled_drops_score_to_2(self):
        companies = [_company("101", **{UF_SITE: "https://x"})]
        scored = score_companies(companies, [], [], [], [], {})
        self.assertEqual(scored[0].score, 2)
        self.assertFalse(scored[0].empty_uf)
        # links всё ещё пусты → safe_to_delete остаётся True
        self.assertTrue(scored[0].safe_to_delete)

    def test_company_with_links_is_not_safe_even_if_uf_empty(self):
        companies = [_company("102")]
        scored = score_companies(
            companies,
            [{"ID": "1", "COMPANY_ID": "102"}],
            [], [], [], {},
        )
        self.assertFalse(scored[0].empty_links)
        self.assertFalse(scored[0].safe_to_delete)
        self.assertEqual(scored[0].score, 2)  # inn + uf empty, links НЕ empty

    def test_inn_from_requisite_drops_empty_inn_flag(self):
        companies = [_company("103")]
        reqs = [{"ENTITY_ID": "103", "RQ_INN": "7707123456", "RQ_OGRN": ""}]
        scored = score_companies(companies, [], [], [], reqs, {})
        self.assertEqual(scored[0].inn, "7707123456")
        self.assertFalse(scored[0].empty_inn)

    def test_requisite_without_inn_keeps_empty_inn_true(self):
        companies = [_company("104")]
        reqs = [{"ENTITY_ID": "104", "RQ_INN": "", "RQ_OGRN": "1027700000000"}]
        scored = score_companies(companies, [], [], [], reqs, {})
        self.assertEqual(scored[0].inn, "")
        self.assertTrue(scored[0].empty_inn)

    def test_select_for_upload_filters_score_lt_2_unless_safe(self):
        # компания со score=1, но НЕ safe (есть deal) — не должна попасть
        companies = [_company("105", **{UF_SITE: "x", UF_CITY: "y"})]  # 2 UF filled → empty_uf=False
        reqs = [{"ENTITY_ID": "105", "RQ_INN": "7707123456"}]  # INN есть → empty_inn=False
        deals = [{"ID": "1", "COMPANY_ID": "105"}]  # links есть → empty_links=False, safe=False
        scored = score_companies(companies, deals, [], [], reqs, {})
        self.assertEqual(scored[0].score, 0)
        self.assertFalse(scored[0].safe_to_delete)
        self.assertEqual(select_for_upload(scored), [])

    def test_select_for_upload_sorts_score_desc_then_date_asc(self):
        companies = [
            _company("a", DATE_CREATE="2022-05-01"),
            _company("b", DATE_CREATE="2019-01-01"),
            _company("c", DATE_CREATE="2021-03-01", **{UF_CITY: "X"}),
        ]
        scored = score_companies(companies, [], [], [], [], {})
        filtered = select_for_upload(scored)
        self.assertEqual([r.id for r in filtered], ["b", "a", "c"])  # 3,3,2 — b старше a

    def test_summary_counts_aggregates(self):
        companies = [
            _company("a"),                                 # score=3, safe
            _company("b"),                                 # score=3, safe
            _company("c", **{UF_CITY: "X"}),               # score=2, safe
        ]
        scored = score_companies(companies, [], [], [], [], {})
        s = summary_counts(select_for_upload(scored))
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["score_3"], 2)
        self.assertEqual(s["score_2"], 1)
        self.assertEqual(s["safe"], 3)
        self.assertEqual(s["score_3_safe"], 2)


if __name__ == "__main__":
    unittest.main()
