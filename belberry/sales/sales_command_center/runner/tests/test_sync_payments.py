from src.sync_payments import _month_num, _num, build_payment_rows


def test_num_parses_nbsp_thousands():
    assert _num("1\xa0005\xa0002") == 1005002.0
    assert _num("24 816") == 24816.0
    assert _num("") is None
    assert _num(None) is None


def test_month_num_ru_any_case():
    assert _month_num("МАЙ") == 5
    assert _month_num("январь") == 1
    assert _month_num("Июнь") == 6
    assert _month_num("") is None


def test_build_payment_rows_maps_columns():
    raw = [
        ["cdz-alter.ru", "Телемаркетинг", "Продажи", "Деговцова", "SEO",
         "80\xa0000", "80\xa0000", "640\xa0000", "640\xa0000",
         "07.05.2026", "безнал", "Щемелёва", "Belberry", "Май", "2026"],
        ["", "x", "Продажи"],  # без проекта — пропуск
    ]
    rows = build_payment_rows(raw)
    assert len(rows) == 1
    r = rows[0]
    assert r["project"] == "cdz-alter.ru"
    assert r["dept"] == "Продажи"
    assert r["kd_no_vat"] == 80000.0
    assert r["dd_no_vat"] == 640000.0
    assert r["pay_month"] == 5
    assert r["pay_year"] == 2026
    assert r["brand"] == "Belberry"
