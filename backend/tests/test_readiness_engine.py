from __future__ import annotations

from app.readiness import ReadinessInputs, baseline_from_coverage, compute


def _inputs(**overrides):
    base = dict(
        competency_mastery=[0.5, 0.6, 0.4],
        competency_attempts=[1, 1, 0],
        recent_dimension_scores=[
            {"accuracy": 0.6, "completeness": 0.5, "communication": 0.7, "evidence": 0.4, "conciseness": 0.6, "response_time": 0.8},
            {"accuracy": 0.7, "completeness": 0.7, "communication": 0.8, "evidence": 0.6, "conciseness": 0.7, "response_time": 0.7},
        ],
        weakness_severity={"knowledge": 0.2, "communication": 0.1},
        difficulty_history=[3, 3, 4],
        total_competencies=3,
    )
    base.update(overrides)
    return ReadinessInputs(**base)


def test_all_seven_dimensions_present() -> None:
    scores = compute(_inputs())
    for key in (
        "overall","knowledge","communication","evidence","conciseness","pressure","consistency","coverage",
    ):
        assert key in scores
        assert 0.0 <= scores[key] <= 1.0


def test_deterministic_given_same_inputs() -> None:
    a = compute(_inputs())
    b = compute(_inputs())
    assert a == b


def test_coverage_reflects_attempted_ratio() -> None:
    all_attempted = compute(_inputs(competency_attempts=[1, 1, 1]))
    none_attempted = compute(_inputs(competency_attempts=[0, 0, 0]))
    assert all_attempted["coverage"] == 1.0
    assert none_attempted["coverage"] == 0.0
    assert all_attempted["overall"] > none_attempted["overall"]


def test_weakness_penalty_lowers_overall() -> None:
    low = compute(_inputs(weakness_severity={"knowledge": 0.05}))
    high = compute(_inputs(weakness_severity={"knowledge": 0.95}))
    assert high["overall"] < low["overall"]


def test_baseline_is_modest_without_performance() -> None:
    scores = baseline_from_coverage(20, {"technology": 10, "metric": 3, "role": 1})
    assert scores["overall"] < 0.6
    assert scores["coverage"] == 0.0
    assert 0.0 <= scores["knowledge"] <= 0.6
