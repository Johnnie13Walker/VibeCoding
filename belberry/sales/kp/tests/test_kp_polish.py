"""Тесты гардов LLM-полировки (pure, без сети)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kp_polish import (  # noqa: E402
    allowed_numbers,
    extract_numbers,
    split_slides,
    tag_multiset,
    validate_slide,
)

ORIG = ('<section class="slide"><div class="card"><h3>Заголовок</h3>'
        '<p>Визитов 21 200, конверсия 1,41%.</p></div></section>')
DATA = '{"metrika": {"visits": 21200, "conv": 1.41, "leads": 172}}'


def test_tag_multiset_counts_open_and_close():
    assert tag_multiset(ORIG) == {"section": 2, "div": 2, "h3": 2, "p": 2}


def test_extract_numbers_normalizes():
    assert extract_numbers("21 200 визитов, 1,41% и 95 000 ₽") == {"21200", "1.41", "95000"}


def test_validate_accepts_text_only_rewrite():
    new = ORIG.replace("Заголовок", "Радиогиды: рост заявок из поиска")
    assert validate_slide(ORIG, new, DATA) is None


def test_validate_rejects_structure_change():
    new = ORIG.replace("<p>", "<p><b>").replace("</p>", "</b></p>")
    assert "структура" in validate_slide(ORIG, new, DATA)


def test_validate_rejects_invented_number():
    new = ORIG.replace("21 200", "37 500")  # 37500 нет ни в данных, ни в слайде
    assert "выдуманные числа" in validate_slide(ORIG, new, DATA)


def test_validate_allows_numbers_from_data():
    new = ORIG.replace("конверсия 1,41%", "заявок 172, конверсия 1,41%")
    # 172 есть в данных, p-тег не менялся
    assert validate_slide(ORIG, new, DATA) is None


def test_validate_rejects_guarantee_and_placeholder():
    assert validate_slide(ORIG, ORIG.replace("Заголовок", "Гарантируем рост"), DATA)
    assert validate_slide(ORIG, ORIG.replace("Заголовок", "{{X}}"), DATA)


def test_small_ints_allowed():
    assert "12" in allowed_numbers("<section></section>", "{}")  # нумерация слайдов


def test_split_slides():
    html = ORIG + "\n" + ORIG.replace("Заголовок", "Второй")
    assert len(split_slides(html)) == 2

def test_locked_text_rejected_on_change():
    from kp_polish import locked_texts, validate_slide
    orig = ('<section class="slide"><div data-lock="1">+12–23 заявок</div>'
            '<p>текст</p></section>')
    assert locked_texts(orig) == ["+12–23 заявок"]
    ok = orig.replace("текст", "новый текст про клиента")
    assert validate_slide(orig, ok, "{}") is None
    bad = orig.replace("+12–23 заявок", "4 761 визит")
    assert "data-lock" in validate_slide(orig, bad, '{"x": 4761}')


def test_images_protected_from_llm():
    from kp_polish import protect_images, restore_images
    html = '<img src="data:image/png;base64,AAAA"/><img src="data:image/png;base64,BBBB"/>'
    prot, stash = protect_images(html)
    assert "base64" not in prot and len(stash) == 2
    assert restore_images(prot, stash) == html
    assert restore_images(prot.replace("__IMG_1__", "x"), stash) is None  # токен потерян → брак
