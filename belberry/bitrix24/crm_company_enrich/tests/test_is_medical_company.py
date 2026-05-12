"""Тесты для is_medical_company (классификатор бренда Belberry vs Acoola Team).

Контракт:
  - True  → Belberry (UF_CRM_684FE59BA3C8C = 2444, медицинский сегмент)
  - False → Acoola Team (UF_CRM_684FE59BA3C8C = 2442, всё кроме медицины)

Дефолт при отсутствии сигналов / нейтральном тексте → True (Belberry — основной
сегмент). Медицинский keyword перевешивает non-medical (см. кейс
«Клиника-Сервис / Автосервис клиники»).
"""
from __future__ import annotations

import pytest

from crm_company_enrich.models import is_medical_company


@pytest.mark.parametrize(
    "title, name, web, expected",
    [
        # ----- Medical (Belberry) -----
        ("ООО Профидент", "Семейная стоматология", "pfdent.ru", True),
        ("Zaffiro Clinic", None, None, True),
        ("Центр МРТ в Москве", None, "mrt.ru", True),
        ("УЗИ на коломенской", None, None, True),
        ("OncoCareClinic 308", None, "oncocareclinic.ru", True),
        ("youcanlive.ru", "youcanlive.ru", None, True),
        ("ООО АЛЬЯНС-МЕД", None, None, True),
        # медицинская adjacency: «Фрезерный центр» — стоматологическая фрезеровка
        ("LabPrestige", "Фрезерный центр LabPrestige", None, True),

        # ----- Non-medical (Acoola Team) -----
        ("ИП Соколов", "Автосервис BMW ProfiService", None, False),
        ("ООО Кредит", "Быстро Деньги МФО", "bistrodengi.ru", False),
        ("Мебельный магазин ЛДСП", None, None, False),

        # ----- Edge: empty / unknown → True (default Belberry) -----
        ("", None, None, True),
        (None, None, None, True),
        ("ООО Ромашка", None, None, True),

        # ----- Medical keyword выигрывает у non-medical в том же blob -----
        ("ООО Клиника-Сервис", "Автосервис клиники", None, True),
    ],
)
def test_is_medical_company(title, name, web, expected):
    assert is_medical_company(bitrix_title=title, discovered_name=name, web=web) == expected


def test_domain_signal_alone_can_classify():
    """Только domain без title/name → должно классифицировать."""
    assert is_medical_company(domain="oncocareclinic.ru") is True
    assert is_medical_company(domain="bistrodengi.ru", bitrix_title="ООО Мфо") is False


def test_case_insensitive_matching():
    """Регистр не важен."""
    assert is_medical_company(bitrix_title="CLINIC Beverly") is True
    assert is_medical_company(bitrix_title="МЕДИЦИНА24") is True
