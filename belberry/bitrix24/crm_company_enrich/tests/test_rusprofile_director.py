from pathlib import Path

from crm_company_enrich.rusprofile_director import (
    _extract_inn_from_person_url,
    parse_director_from_rusprofile_html,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_director_from_real_rusprofile_snippet():
    html = (FIXTURES / "rusprofile_director_rozhkov.html").read_text(encoding="utf-8")

    info = parse_director_from_rusprofile_html(html)

    assert info is not None
    assert info.inn == "263201428652"
    assert info.full_name == "Рожков Виктор Сергеевич"
    assert info.person_url == "/person/rozhkov-vs-263201428652"


def test_parse_director_with_post_label():
    html = (FIXTURES / "rusprofile_director_ivanov.html").read_text(encoding="utf-8")

    info = parse_director_from_rusprofile_html(html)

    assert info is not None
    assert info.post == "Генеральный директор"


def test_parse_director_missing_inn_url():
    assert parse_director_from_rusprofile_html("<h2>Руководитель</h2><a href='/person/no-inn'>Иванов И.И.</a>") is None


def test_parse_director_short_url_not_inn():
    assert parse_director_from_rusprofile_html("<h2>Руководитель</h2><a href='/person/short-1234'>Иванов И.И.</a>") is None


def test_inn_extraction_with_punctuation_in_slug():
    assert _extract_inn_from_person_url("/person/ivanov-i-v-123456789012") == "123456789012"
