from __future__ import annotations

import pytest

from crm_deal_merge.domain import normalize_domain


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        ("helfbebe.ru", "helfbebe.ru"),
        ("new.cecilplus.ru", "cecilplus.ru"),
        ("ekaterinburg.upclinic.ru", "upclinic.ru"),
        ("www.foo.ru", "foo.ru"),
        ("mido-dent.ru", "midodent.ru"),
        ("midodent.ru", "midodent.ru"),
        ("midodent1.ru", "midodent1.ru"),
        ("shop.straumann.ru", "straumann.ru"),
        ("микаелян.рф", "микаелян.рф"),
        ("Холодный звонок", None),
        ("", None),
        ("smklin.ru — обзвон", "smklin.ru"),
        ("https://www.example.com/page", "example.com"),
        ("msk.clinic-info.net", "clinicinfo.net"),
        ("kazan.some-clinic.org", "someclinic.org"),
        ("pushkino.test.moscow", "test.moscow"),
        ("korolev.demo.tech", "demo.tech"),
        ("rostov.site.ai", "site.ai"),
        ("perm.brand.io", "brand.io"),
        ("tula.foo-bar.me", "foobar.me"),
        ("ufa.alpha.spb", "alpha.spb"),
        ("no domain here", None),
    ],
)
def test_normalize_domain(input_value: str, expected: str | None) -> None:
    assert normalize_domain(input_value) == expected
