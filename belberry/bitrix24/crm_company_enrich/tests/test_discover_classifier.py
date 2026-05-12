"""Тесты классификации компаний has_valid_inn / empty_inn / no_requisite."""
from __future__ import annotations

from crm_company_enrich.models import CompanyClass, classify_company


def test_no_requisite_when_empty_list():
    assert classify_company([]) == CompanyClass.NO_REQUISITE


def test_has_valid_inn_when_one_requisite_with_valid_inn():
    reqs = [{"ID": "1", "RQ_INN": "7707083893"}]
    assert classify_company(reqs) == CompanyClass.HAS_VALID_INN


def test_empty_inn_when_requisite_has_no_inn():
    reqs = [{"ID": "2", "RQ_INN": ""}]
    assert classify_company(reqs) == CompanyClass.EMPTY_INN


def test_empty_inn_when_requisite_has_invalid_inn():
    reqs = [{"ID": "3", "RQ_INN": "123"}]
    assert classify_company(reqs) == CompanyClass.EMPTY_INN


def test_has_valid_inn_when_at_least_one_requisite_valid():
    reqs = [
        {"ID": "1", "RQ_INN": ""},
        {"ID": "2", "RQ_INN": "770708389300"},
    ]
    assert classify_company(reqs) == CompanyClass.HAS_VALID_INN


def test_empty_inn_when_all_requisites_invalid():
    reqs = [
        {"ID": "1", "RQ_INN": ""},
        {"ID": "2", "RQ_INN": "abc"},
        {"ID": "3", "RQ_INN": None},
    ]
    assert classify_company(reqs) == CompanyClass.EMPTY_INN
