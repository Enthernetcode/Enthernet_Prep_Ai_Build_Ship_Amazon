"""§27 deterministic readiness engine.

Readiness is not an average quiz score. It combines topic mastery, recency,
difficulty, consistency, weakness severity, pressure handling, and coverage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class ReadinessInputs:
    competency_mastery: list[float]         # 0..1, one entry per known competency
    competency_attempts: list[int]          # attempts per competency
    recent_dimension_scores: list[dict[str, float]]  # last N turn evaluations
    weakness_severity: dict[str, float]     # bucket → severity in 0..1
    difficulty_history: list[int]           # 1..6 per recent turn
    total_competencies: int                 # denominator for coverage


def _mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _weighted_recent(values: list[float]) -> float:
    """Exponential recency weighting: newest turn weighted highest."""
    if not values:
        return 0.0
    weights = [math.exp(0.35 * i) for i in range(len(values))]
    total = sum(weights)
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total


def _consistency(values: list[float]) -> float:
    if len(values) < 2:
        return 0.75
    mean = _mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    stddev = math.sqrt(var)
    return max(0.0, min(1.0, 1.0 - stddev * 1.5))


def _coverage(competency_attempts: list[int], total: int) -> float:
    if total <= 0:
        return 0.0
    attempted = sum(1 for a in competency_attempts if a > 0)
    return min(1.0, attempted / total)


def _difficulty_factor(difficulty_history: list[int]) -> float:
    if not difficulty_history:
        return 0.5
    avg = _mean([d / 6.0 for d in difficulty_history])
    return max(0.3, min(1.15, 0.7 + avg * 0.5))


def compute(inputs: ReadinessInputs) -> dict[str, Any]:
    knowledge_mean = _mean(inputs.competency_mastery)

    def dim(key: str, default: float = 0.6) -> list[float]:
        return [row.get(key, default) for row in inputs.recent_dimension_scores]

    accuracy_recent = _weighted_recent(dim("accuracy"))
    completeness_recent = _weighted_recent(dim("completeness"))
    knowledge = round(
        max(0.0, min(1.0, 0.6 * accuracy_recent + 0.25 * completeness_recent + 0.15 * knowledge_mean)),
        4,
    )

    communication = round(
        max(0.0, min(1.0, _weighted_recent(dim("communication")))),
        4,
    )
    evidence = round(
        max(0.0, min(1.0, _weighted_recent(dim("evidence")))),
        4,
    )
    conciseness = round(
        max(0.0, min(1.0, _weighted_recent(dim("conciseness")))),
        4,
    )
    pressure = round(
        max(
            0.0,
            min(
                1.0,
                _weighted_recent(dim("response_time", 0.7))
                * (1.0 - min(1.0, inputs.weakness_severity.get("pressure", 0.0) * 0.5)),
            ),
        ),
        4,
    )
    consistency = round(_consistency(dim("accuracy")), 4)
    coverage = round(_coverage(inputs.competency_attempts, inputs.total_competencies), 4)

    weights = {
        "knowledge": 0.30,
        "communication": 0.15,
        "evidence": 0.15,
        "conciseness": 0.05,
        "pressure": 0.10,
        "consistency": 0.10,
        "coverage": 0.15,
    }
    scores = {
        "knowledge": knowledge,
        "communication": communication,
        "evidence": evidence,
        "conciseness": conciseness,
        "pressure": pressure,
        "consistency": consistency,
        "coverage": coverage,
    }
    weighted = sum(scores[k] * w for k, w in weights.items())
    overall = round(max(0.0, min(1.0, weighted * _difficulty_factor(inputs.difficulty_history))), 4)

    weakness_penalty = 0.0
    if inputs.weakness_severity:
        top = max(inputs.weakness_severity.values())
        weakness_penalty = min(0.15, top * 0.2)
    overall = round(max(0.0, overall - weakness_penalty), 4)

    return {
        "overall": overall,
        **scores,
        "detail": {
            "knowledge_mean": round(knowledge_mean, 4),
            "difficulty_factor": round(_difficulty_factor(inputs.difficulty_history), 4),
            "weakness_penalty": round(weakness_penalty, 4),
            "weights": weights,
        },
    }


def baseline_from_coverage(total: int, extracted_kinds: dict[str, int]) -> dict[str, Any]:
    """Baseline readiness — computed before any turn.

    Uploaded material provides *potential*; readiness stays modest until
    demonstrated performance exists (§23).
    """
    if total == 0:
        knowledge = 0.15
    else:
        knowledge = min(0.55, 0.25 + math.log10(1 + total) * 0.15)
    coverage = 0.0  # nothing attempted yet
    evidence = min(0.7, 0.3 + 0.05 * extracted_kinds.get("metric", 0))
    communication = 0.5
    conciseness = 0.5
    pressure = 0.5
    consistency = 0.5
    weights = {
        "knowledge": 0.30,
        "communication": 0.15,
        "evidence": 0.15,
        "conciseness": 0.05,
        "pressure": 0.10,
        "consistency": 0.10,
        "coverage": 0.15,
    }
    scores = {
        "knowledge": knowledge,
        "communication": communication,
        "evidence": evidence,
        "conciseness": conciseness,
        "pressure": pressure,
        "consistency": consistency,
        "coverage": coverage,
    }
    overall = round(max(0.0, min(0.55, sum(scores[k] * w for k, w in weights.items()))), 4)
    return {
        "overall": overall,
        **{k: round(v, 4) for k, v in scores.items()},
        "detail": {"baseline": True, "extracted_kinds": extracted_kinds},
    }
