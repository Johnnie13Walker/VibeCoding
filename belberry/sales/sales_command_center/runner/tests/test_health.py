from src.health import compute_health_score


def test_compute_health_score_green_boundary():
    score = compute_health_score(
        [{"operational_score": 10.0}],
        [{"analysis": {"score": 10}}, {"analysis": {"score": 10}}, {"analysis": {"score": 10}}, {"analysis": {"score": 10}}],
        {},
    )

    assert score["score"] == 80
    assert score["level"] == "green"
    assert score["components"]["risk_penalty"] == 0


def test_compute_health_score_amber_boundary():
    score = compute_health_score(
        [{"operational_score": 5.0}],
        [{"analysis": {"score": 5}}, {"analysis": {"score": 5}}],
        {},
    )

    assert score["score"] == 40
    assert score["level"] == "amber"


def test_compute_health_score_red_with_capped_risk_penalty():
    stale = {
        "Подготовка КП": [
            {"opportunity": 1_000_000},
            {"opportunity": 1_000_000},
            {"opportunity": 1_000_000},
            {"opportunity": 1_000_000},
            {"opportunity": 1_000_000},
        ]
    }

    score = compute_health_score(
        [{"operational_score": 2.0}],
        [{"analysis": {"score": 4}}],
        stale,
    )

    assert score["score"] == 0
    assert score["level"] == "red"
    assert score["components"]["risk_penalty"] == 25
    assert score["components"]["stale_count"] == 5
