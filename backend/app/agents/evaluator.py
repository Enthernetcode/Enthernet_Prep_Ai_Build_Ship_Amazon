from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult
from app.providers.base import GenerationRequest, LLMProvider

logger = logging.getLogger(__name__)


# §26 default rubric weights.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "accuracy": 0.30,
    "completeness": 0.20,
    "relevance": 0.15,
    "conciseness": 0.10,
    "evidence": 0.10,
    "communication": 0.10,
    "response_time": 0.05,
}

# Mode overrides — normalized on use.
_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "mock_interview": _DEFAULT_WEIGHTS,
    "final_boss": {
        "accuracy": 0.30,
        "completeness": 0.20,
        "relevance": 0.15,
        "conciseness": 0.10,
        "evidence": 0.10,
        "communication": 0.10,
        "response_time": 0.05,
    },
    "pitch": {
        "clarity": 0.25,
        "evidence": 0.20,
        "business_impact": 0.20,
        "conciseness": 0.15,
        "consistency": 0.20,
    },
    "weakness_drill": {
        "accuracy": 0.40,
        "completeness": 0.25,
        "relevance": 0.15,
        "communication": 0.10,
        "evidence": 0.10,
    },
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\+\-#\.]{2,}")
_FILLER = {
    "um","uh","like","kinda","sorta","basically","actually","literally",
    "you know","i guess","kind of","sort of",
}
_EVIDENCE_HINTS = {
    "for example","for instance","specifically","in production","we shipped",
    "we measured","the result was","p95","p99","latency","throughput","%","percent",
    "million","thousand","reduced","increased","improved",
}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


def _norm(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


def _lexical_overlap(answer: str, grounding_text: str) -> float:
    a = set(_tokens(answer))
    g = set(_tokens(grounding_text))
    if not g:
        return 0.5
    return len(a & g) / max(1, len(g))


def _conciseness(answer: str) -> float:
    words = answer.split()
    n = len(words)
    if n == 0:
        return 0.0
    # Sweet spot 40–160 words; penalize very short and very long.
    if 40 <= n <= 160:
        base = 1.0
    elif n < 40:
        base = n / 40.0
    else:
        base = max(0.3, 1.0 - (n - 160) / 400.0)
    lowered = answer.lower()
    filler_hits = sum(lowered.count(f) for f in _FILLER)
    penalty = min(0.4, filler_hits * 0.05)
    return max(0.0, min(1.0, base - penalty))


def _completeness(answer: str, difficulty: int) -> float:
    words = len(answer.split())
    target = 30 + difficulty * 20  # d1→50, d6→150
    if words == 0:
        return 0.0
    ratio = words / target
    if ratio >= 1.0:
        return min(1.0, 0.6 + 0.4 * (min(ratio, 2.0) - 1.0))
    return max(0.15, ratio * 0.7)


def _evidence(answer: str) -> float:
    lowered = answer.lower()
    hits = sum(1 for h in _EVIDENCE_HINTS if h in lowered)
    numbers = len(re.findall(r"\b\d[\d,\.]*\b", answer))
    raw = hits * 0.15 + numbers * 0.1
    return max(0.0, min(1.0, raw))


def _communication(answer: str) -> float:
    if not answer.strip():
        return 0.0
    sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
    if not sentences:
        return 0.3
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    # Prefer avg sentence length 8–22 words.
    if 8 <= avg <= 22:
        base = 1.0
    elif avg < 8:
        base = 0.5 + avg / 16.0
    else:
        base = max(0.3, 1.0 - (avg - 22) / 30.0)
    caps_ratio = sum(1 for c in answer if c.isupper()) / max(1, len(answer))
    if caps_ratio > 0.4:
        base -= 0.3
    return max(0.0, min(1.0, base))


def _relevance(answer: str, topic: str) -> float:
    if not topic:
        return 0.6
    topic_tokens = set(_tokens(topic))
    if not topic_tokens:
        return 0.6
    answer_tokens = set(_tokens(answer))
    overlap = len(topic_tokens & answer_tokens) / max(1, len(topic_tokens))
    return max(0.15, min(1.0, 0.3 + 0.7 * overlap))


def _response_time(seconds: float | None, difficulty: int) -> float:
    if seconds is None:
        return 0.7
    target = 15 + difficulty * 20  # d1→35s, d6→135s
    if seconds <= target:
        return 1.0
    over = seconds - target
    return max(0.2, 1.0 - over / (target * 2))


def _accuracy(answer: str, grounding_text: str, topic: str) -> float:
    if not answer.strip():
        return 0.0
    lex = _lexical_overlap(answer, grounding_text or topic)
    denials = sum(
        1
        for phrase in ("i don't know", "not sure", "no idea", "cannot answer")
        if phrase in answer.lower()
    )
    return max(0.0, min(1.0, 0.25 + 0.75 * lex - denials * 0.3))


class EvaluatorAgent(Agent):
    """§15 Evaluator Agent — multi-dimensional rubric scoring."""

    name = "evaluator"
    description = "Evaluate an answer across independent rubric dimensions."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        answer: str = tools["answer"]
        topic: str = tools.get("topic", "")
        grounding_text: str = tools.get("grounding_text", "")
        difficulty: int = int(tools.get("difficulty", context.difficulty or 3))
        seconds: float | None = tools.get("seconds_taken")
        mode: str = tools.get("mode", "mock_interview")

        dims_all: dict[str, float] = {
            "accuracy": _accuracy(answer, grounding_text, topic),
            "completeness": _completeness(answer, difficulty),
            "relevance": _relevance(answer, topic),
            "conciseness": _conciseness(answer),
            "evidence": _evidence(answer),
            "communication": _communication(answer),
            "response_time": _response_time(seconds, difficulty),
            "consistency": 0.75,  # populated over multiple turns by ReadinessEngine
            "clarity": _communication(answer),
            "business_impact": _evidence(answer),
        }

        weights = _norm(_MODE_WEIGHTS.get(mode, _DEFAULT_WEIGHTS))
        overall = sum(dims_all[k] * w for k, w in weights.items() if k in dims_all)

        # Persisted dimensions include everything the readiness engine needs.
        persisted = {k: round(dims_all[k], 4) for k in (
            "accuracy","completeness","relevance","conciseness","evidence",
            "communication","response_time","consistency","clarity","business_impact",
        )}

        # Optional LLM-written coach rationale on top of the deterministic
        # scores. Scores remain the source of truth; rationale is additive.
        rationale: str | None = None
        rationale_source = "none"
        llm_provider: LLMProvider | None = tools.get("llm_provider")
        llm_model: str = tools.get("llm_model") or ""
        question: str = tools.get("question") or ""
        if llm_provider is not None and getattr(llm_provider, "name", "mock") != "mock":
            rationale = await _llm_rationale(
                llm_provider,
                llm_model,
                question=question,
                answer=answer,
                topic=topic,
                grounding_text=grounding_text,
                persisted=persisted,
                overall=round(overall, 4),
            )
            if rationale:
                rationale_source = llm_provider.name

        result: dict[str, Any] = {
            "overall": round(overall, 4),
            "dimensions": persisted,
            "weights": weights,
            "mode": mode,
            "rationale_source": rationale_source,
        }
        if rationale:
            result["rationale"] = rationale
        return AgentResult(
            agent=self.name,
            status="success",
            confidence=round(overall, 4),
            result=result,
        )


_SYSTEM_COACH = (
    "You are a professional interview coach. In 1-2 short sentences, give the "
    "candidate honest, specific feedback — one thing they did well and one "
    "concrete thing to tighten. Do not restate the scores. Do not restate the "
    "question. No preamble. Under 60 words."
)


async def _llm_rationale(
    provider: LLMProvider,
    model: str,
    *,
    question: str,
    answer: str,
    topic: str,
    grounding_text: str,
    persisted: dict[str, float],
    overall: float,
) -> str | None:
    scores_summary = ", ".join(
        f"{k}={v:.2f}"
        for k, v in persisted.items()
        if k in ("accuracy", "completeness", "evidence", "conciseness", "communication")
    )
    prompt = (
        f"Topic: {topic}\n"
        f'Interviewer asked: "{question}"\n'
        f'Candidate answered: "{answer[:1200]}"\n'
        + (
            f"Source material the candidate wrote about this topic:\n{grounding_text[:600]}\n"
            if grounding_text
            else ""
        )
        + f"\nRubric scores (0-1): {scores_summary}. Overall: {overall:.2f}.\n\n"
        "Give the candidate 1-2 sentences of coaching."
    )
    try:
        resp = await provider.generate(
            GenerationRequest(
                model=model or "gpt-4o-mini",
                prompt=prompt,
                system=_SYSTEM_COACH,
                max_tokens=140,
                temperature=0.4,
            )
        )
    except Exception as exc:
        logger.warning("Evaluator LLM rationale failed: %s", exc)
        return None
    text = (resp.text or "").strip()
    return text or None
