from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.evaluator import EvaluatorAgent


@pytest.mark.asyncio
async def test_all_dimensions_present_in_zero_to_one() -> None:
    agent = EvaluatorAgent()
    result = await agent.execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": (
                "Kubernetes uses CNI plugins to configure pod networking. "
                "For example, at my last job we ran Cilium in production; "
                "we reduced east-west latency by 30% versus the default. "
                "The trade-off was operator complexity."
            ),
            "topic": "kubernetes networking",
            "grounding_text": "Kubernetes networking is powered by CNI plugins.",
            "difficulty": 3,
            "seconds_taken": 45,
            "mode": "mock_interview",
        },
    )
    assert result.status == "success"
    dims = result.result["dimensions"]
    for name in (
        "accuracy","completeness","relevance","conciseness","evidence",
        "communication","response_time","consistency","clarity","business_impact",
    ):
        assert 0.0 <= dims[name] <= 1.0, f"{name}={dims[name]}"
    assert 0.0 <= result.result["overall"] <= 1.0


@pytest.mark.asyncio
async def test_i_dont_know_scores_low_on_accuracy() -> None:
    result = await EvaluatorAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": "I don't know.",
            "topic": "kubernetes",
            "grounding_text": "Kubernetes uses CNI plugins.",
            "difficulty": 3,
            "mode": "mock_interview",
        },
    )
    assert result.result["dimensions"]["accuracy"] < 0.3
    assert result.result["overall"] < 0.5


@pytest.mark.asyncio
async def test_mode_weights_are_normalised() -> None:
    result = await EvaluatorAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": "A short answer that mentions the topic clearly.",
            "topic": "topic",
            "grounding_text": "topic reference text",
            "difficulty": 2,
            "mode": "final_boss",
        },
    )
    weights = result.result["weights"]
    assert 0.99 <= sum(weights.values()) <= 1.01
