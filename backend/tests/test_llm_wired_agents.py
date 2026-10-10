"""Verify that when a non-mock LLM provider is passed to the Examiner /
Evaluator, the provider is actually called and its text is used.

The deterministic path still runs — the LLM is purely additive (question
rephrasing + evaluation rationale). Both tests use a fake LLM provider
instead of the real OpenAI/Bedrock SDK so there's no live API cost."""
from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.evaluator import EvaluatorAgent
from app.agents.examiner import ExaminerAgent
from app.providers.base import GenerationResponse, LLMProvider


class FakeLLM(LLMProvider):
    """Minimal LLM provider that records every generate() call."""

    def __init__(
        self,
        name: str,
        canned: str = "",
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._canned = canned
        self._error = error
        self.calls: list = []

    async def generate(self, request):  # type: ignore[override]
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return GenerationResponse(
            text=self._canned,
            model=request.model,
            tokens_input=50,
            tokens_output=20,
            finish_reason="stop",
        )


_CANDIDATES = [
    {
        "id": "cmp-1",
        "kind": "technology",
        "label": "kubernetes",
        "confidence": 0.9,
        "mastery": 0.3,
        "attempts": 0,
        "weakness_severity": 0.0,
        "source_document_id": "doc-1",
        "source_chunk_ordinal": 0,
    }
]


# ─── Examiner ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_examiner_uses_llm_when_non_mock_provider_present() -> None:
    fake = FakeLLM(name="openai", canned="How have you used Kubernetes in production?")
    result = await ExaminerAgent().execute(
        AgentContext(user_id="u", project_id="p", goal_type="job_interview"),
        tools={
            "candidates": _CANDIDATES,
            "difficulty": 3,
            "seed": 1,
            "llm_provider": fake,
            "llm_model": "gpt-4o-mini",
            "grounding_text": "We ran EKS clusters with Argo CD...",
        },
    )
    assert result.status == "success"
    assert result.result["question"] == "How have you used Kubernetes in production?"
    assert result.result["question_source"] == "openai"
    assert len(fake.calls) == 1
    sent = fake.calls[0]
    assert "kubernetes" in sent.prompt.lower()
    assert sent.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_examiner_falls_back_to_template_when_llm_errors() -> None:
    fake = FakeLLM(name="openai", error=RuntimeError("boom"))
    result = await ExaminerAgent().execute(
        AgentContext(user_id="u", project_id="p", goal_type="job_interview"),
        tools={
            "candidates": _CANDIDATES,
            "difficulty": 3,
            "seed": 1,
            "llm_provider": fake,
            "llm_model": "gpt-4o-mini",
        },
    )
    assert result.status == "success"
    assert "kubernetes" in result.result["question"].lower()
    assert result.result["question_source"] == "template"


@pytest.mark.asyncio
async def test_examiner_skips_llm_when_mock_provider() -> None:
    fake = FakeLLM(name="mock", canned="should not be used")
    result = await ExaminerAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "candidates": _CANDIDATES,
            "difficulty": 2,
            "seed": 0,
            "llm_provider": fake,
            "llm_model": "ignored",
        },
    )
    assert result.result["question_source"] == "template"
    assert fake.calls == []


# ─── Evaluator ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluator_attaches_llm_rationale_when_provider_live() -> None:
    fake = FakeLLM(
        name="openai",
        canned="Good concrete example. Next time, tighten the first sentence.",
    )
    result = await EvaluatorAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": "I built AWS Kubernetes clusters and improved deploy time 70%.",
            "topic": "kubernetes",
            "grounding_text": "AWS Kubernetes production experience",
            "difficulty": 3,
            "seconds_taken": 40,
            "mode": "mock_interview",
            "question": "Describe a project where you used Kubernetes.",
            "llm_provider": fake,
            "llm_model": "gpt-4o-mini",
        },
    )
    assert result.status == "success"
    assert result.result["rationale_source"] == "openai"
    assert result.result["rationale"].startswith("Good concrete example")
    for dim in ("accuracy", "completeness", "communication"):
        assert 0.0 <= result.result["dimensions"][dim] <= 1.0
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_evaluator_omits_rationale_when_llm_errors() -> None:
    fake = FakeLLM(name="openai", error=RuntimeError("rate limited"))
    result = await EvaluatorAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": "A short answer.",
            "topic": "kubernetes",
            "grounding_text": "",
            "difficulty": 2,
            "mode": "mock_interview",
            "question": "Define it.",
            "llm_provider": fake,
            "llm_model": "gpt-4o-mini",
        },
    )
    assert "rationale" not in result.result
    assert result.result["rationale_source"] == "none"


@pytest.mark.asyncio
async def test_evaluator_skips_llm_for_mock_provider() -> None:
    fake = FakeLLM(name="mock", canned="unused")
    result = await EvaluatorAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={
            "answer": "Something.",
            "topic": "x",
            "mode": "mock_interview",
            "llm_provider": fake,
            "llm_model": "ignored",
        },
    )
    assert fake.calls == []
    assert result.result["rationale_source"] == "none"
    assert "rationale" not in result.result
