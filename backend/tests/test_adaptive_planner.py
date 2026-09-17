from __future__ import annotations

import pytest

from app.agents.adaptive import AdaptivePlannerAgent
from app.agents.base import AgentContext


CTX = AgentContext(user_id="u", project_id="p")


@pytest.mark.asyncio
async def test_strong_answer_increases_difficulty() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={"overall": 0.9, "difficulty": 3, "recent_scores": [0.8, 0.85]},
    )
    assert r.result["action"] == "increase_difficulty"
    assert r.result["next_difficulty"] == 4


@pytest.mark.asyncio
async def test_partial_answer_asks_follow_up() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={"overall": 0.6, "difficulty": 4, "recent_scores": [0.55]},
    )
    assert r.result["action"] == "follow_up"
    assert r.result["next_difficulty"] == 4


@pytest.mark.asyncio
async def test_repeated_low_scores_trigger_coach() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={
            "overall": 0.2,
            "difficulty": 3,
            "recent_scores": [0.15, 0.2],  # last two both below 0.35
        },
    )
    assert r.result["action"] == "coach_intervention"
    assert r.result["coach_note"] is not None


@pytest.mark.asyncio
async def test_final_boss_suppresses_coach_note() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={
            "overall": 0.2,
            "difficulty": 3,
            "recent_scores": [0.15, 0.2],
            "mode": "final_boss",
        },
    )
    # Action can still fire, but no spoken coach note in Final Boss.
    assert r.result["coach_note"] is None


@pytest.mark.asyncio
async def test_finish_when_max_turns_reached() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={
            "overall": 0.7,
            "difficulty": 3,
            "recent_scores": [0.7],
            "turns_taken": 8,
            "max_turns": 8,
        },
    )
    assert r.result["action"] == "finish"
    assert r.result["should_finish"] is True


@pytest.mark.asyncio
async def test_high_weakness_biases_toward_mastery() -> None:
    r = await AdaptivePlannerAgent().execute(
        CTX,
        tools={
            "overall": 0.9,  # would normally increase difficulty
            "difficulty": 3,
            "recent_scores": [0.9],
            "weakness_severity": 0.85,
        },
    )
    assert r.result["action"] == "follow_up"
    assert r.result["next_difficulty"] == 3
