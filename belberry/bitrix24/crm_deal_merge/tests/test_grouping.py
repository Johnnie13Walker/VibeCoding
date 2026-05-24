from __future__ import annotations

from crm_deal_merge.grouping import group_deals


def _deal(id_: int, company_id: str, title: str, stage: str, modified: str) -> dict:
    return {
        "ID": str(id_),
        "COMPANY_ID": company_id,
        "TITLE": title,
        "STAGE_ID": stage,
        "DATE_MODIFY": modified,
    }


def test_grouping_and_winner_selection() -> None:
    deals = [
        _deal(1, "10", "www.foo.ru", "C38:NEW", "2026-01-01T10:00:00+03:00"),
        _deal(2, "10", "foo.ru повтор", "C50:NEW", "2026-01-01T09:00:00+03:00"),
        _deal(3, "20", "bar.ru old", "C38:NEW", "2026-01-01T09:00:00+03:00"),
        _deal(4, "20", "bar.ru new", "C38:NEW", "2026-01-01T11:00:00+03:00"),
        _deal(5, "30", "baz.ru a", "C38:NEW", "2026-01-01T12:00:00+03:00"),
        _deal(6, "30", "baz.ru b", "C38:NEW", "2026-01-01T12:00:00+03:00"),
        _deal(7, "40", "Холодный звонок", "C38:NEW", "2026-01-01T12:00:00+03:00"),
        _deal(8, "40", "Лариса напомнила", "C38:NEW", "2026-01-01T13:00:00+03:00"),
        _deal(9, "0", "orphan.ru", "C38:NEW", "2026-01-01T13:00:00+03:00"),
        _deal(10, "", "orphan2.ru", "C50:NEW", "2026-01-01T13:00:00+03:00"),
    ]

    groups, orphans = group_deals(deals)
    by_key = {(g.company_id, g.domain): g for g in groups}

    assert len(orphans) == 2
    assert by_key[("10", "foo.ru")].winner["ID"] == "2"
    assert [d["ID"] for d in by_key[("10", "foo.ru")].losers] == ["1"]
    assert by_key[("20", "bar.ru")].winner["ID"] == "4"
    assert by_key[("30", "baz.ru")].winner["ID"] == "6"
    assert by_key[("40", None)].manual is True
