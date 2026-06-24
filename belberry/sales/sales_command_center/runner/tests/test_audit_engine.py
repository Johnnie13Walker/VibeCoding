"""Юнит-тесты детерминированной логики аудита: recovery_score и теги провалов.
Чистые функции — без Bitrix, без LLM, без реальных данных клиентов."""

from src import audit_engine as ae


def _base_signals(**over):
    sig = {
        "stage_id": "C10:UC_4SJOE4", "stage_semantic": "P", "death_stage": "",
        "lost_reason_id": "", "is_spam": False, "closed": False,
        "opportunity": 0, "company_revenue": 0,
        "kp_cards": 0, "kp_via_pitch": False, "kp_sent": False, "had_defense": False,
        "meetings_total": 0, "briefs_total": 0, "calls_total": 0,
        "handover_count": 0, "responsibles_chain": [],
        "last_contact": None, "days_since_contact": None,
        "contact_lost": False, "competitor_won": False, "budget_objection": False,
        "dm_name": None, "dm_phone": None,
    }
    sig.update(over)
    return sig


def test_score_clamped_and_banded():
    # пустая стухшая сделка → низкий, но не ниже минимума
    sig = _base_signals(days_since_contact=200, competitor_won=True, handover_count=3)
    r = ae.recovery_score(sig)
    assert ae.SCORE_MIN <= r["score"] <= ae.SCORE_MAX
    assert r["band"] == "low"
    assert r["raw"] < r["score"]  # сырой балл ушёл ниже минимума и был зажат


def test_dm_untried_is_positive_lever():
    """Непройденный рычаг ЛПР повышает шанс (есть телефон + защиты не было)."""
    without = ae.recovery_score(_base_signals(dm_phone=None, had_defense=False))["score"]
    with_lever = ae.recovery_score(_base_signals(dm_phone="89990000000", had_defense=False))["score"]
    assert with_lever > without


def test_dm_budget_rejection_only_after_defense():
    """«Нет бюджета» бьёт жёстко только если защита была (сказал ЛПР), иначе мягко."""
    non_dm = ae.recovery_score(_base_signals(budget_objection=True, had_defense=False, kp_sent=True))
    dm = ae.recovery_score(_base_signals(budget_objection=True, had_defense=True))
    assert dm["score"] < non_dm["score"]


def test_expected_value_scales_with_opportunity():
    sig = _base_signals(opportunity=100000, dm_phone="8", company_revenue=5_000_000)
    r = ae.recovery_score(sig)
    assert r["expected_value"] == round(r["score"] / 100 * 100000)


def test_drmannanov_like_profile_is_low_but_not_dead():
    """Профиль #23332: контакт ушёл, защиты не было, ЛПР не тронут, контакт свежий."""
    sig = _base_signals(
        opportunity=108255, company_revenue=16_872_000,
        kp_cards=0, kp_via_pitch=True, kp_sent=True, had_defense=False,
        meetings_total=1, briefs_total=3, handover_count=2,
        days_since_contact=5, contact_lost=True, budget_objection=True,
        dm_phone="89274135383",
    )
    r = ae.recovery_score(sig)
    assert r["band"] in ("low", "mid")
    assert 20 <= r["score"] <= 55  # низкий, но живой за счёт непройденного ЛПР-рычага
    assert r["expected_value"] > 0


def test_failure_tags_cover_known_patterns():
    sig = _base_signals(
        kp_cards=0, kp_sent=True, kp_via_pitch=True, had_defense=False,
        briefs_total=3, handover_count=2, budget_objection=True, contact_lost=True,
    )
    tags = {t["tag"] for t in ae._failure_tags(sig)}
    assert {"KP_NO_CARD", "KP_VIA_PITCH", "NO_DEFENSE", "HANDOVER_NO_CONTEXT",
            "BRIEF_SPRAY", "BUDGET_LABEL", "CONTACT_LOST"} <= tags


def test_single_handover_tag_not_double():
    one = {t["tag"] for t in ae._failure_tags(_base_signals(handover_count=1))}
    two = {t["tag"] for t in ae._failure_tags(_base_signals(handover_count=2))}
    assert "HANDOVER" in one and "HANDOVER_NO_CONTEXT" not in one
    assert "HANDOVER_NO_CONTEXT" in two and "HANDOVER" not in two
