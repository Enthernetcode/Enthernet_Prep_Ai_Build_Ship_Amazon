from __future__ import annotations

import logging
import random
from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult
from app.providers.base import GenerationRequest, LLMProvider

logger = logging.getLogger(__name__)


# §24 difficulty ladder → verb templates.
_TEMPLATES: dict[int, list[str]] = {
    1: [
        "In your own words, what is {label}?",
        "Briefly define {label}.",
    ],
    2: [
        "Explain how {label} works and why it matters.",
        "Walk me through {label} as if I were a new teammate.",
    ],
    3: [
        "Describe a project where you applied {label}. What was the outcome?",
        "How would you use {label} to solve a real problem you have shipped?",
    ],
    4: [
        "Compare {label} with an alternative approach — what trade-offs made you choose it?",
        "Where does {label} break down at scale, and how do you mitigate that?",
    ],
    5: [
        "Defend a controversial design decision you made involving {label}. Would you make it again?",
        "A senior engineer disagrees with your use of {label}. Convince them.",
    ],
    6: [
        "You claimed on your CV to have used {label}. I don't believe you — prove it with specifics.",
        "Two of your prior answers about {label} appear to contradict each other. Which is correct, and why?",
    ],
}

_ROLE_LEAD_IN = {
    "job_interview": "As a candidate for this role, ",
    "pitch": "As the founder pitching this venture, ",
}


def _template_for(kind: str, difficulty: int) -> str:
    difficulty = max(1, min(6, difficulty))
    pool = _TEMPLATES[difficulty]
    if kind == "metric":
        return "The document claims '{label}'. Walk me through how that number was measured."
    if kind == "role":
        return "You mention targeting the role '{label}'. What must you demonstrate to be credible for it?"
    if kind == "fact":
        return "The reference to '{label}' — what is its relevance to the role you are preparing for?"
    return pool[0]


class ExaminerAgent(Agent):
    """§13 Examiner Agent — generates one grounded question per turn."""

    name = "examiner"
    description = "Generate a grounded question from the competency map."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        candidates: list[dict[str, Any]] = tools.get("candidates", [])
        asked_labels: set[str] = {s.lower() for s in tools.get("asked_labels", [])}
        difficulty: int = int(tools.get("difficulty", context.difficulty or 3))
        goal_type: str | None = context.goal_type
        rng = random.Random(tools.get("seed", 0))

        # Score candidates: weak + uncovered + high-confidence first.
        def score(item: dict[str, Any]) -> float:
            mastery = float(item.get("mastery", 0.0))
            severity = float(item.get("weakness_severity", 0.0))
            attempts = int(item.get("attempts", 0))
            conf = float(item.get("confidence", 0.5))
            uncovered = 1.0 if attempts == 0 else 0.0
            return (1.0 - mastery) * 0.5 + severity * 0.3 + uncovered * 0.15 + conf * 0.05

        pool = [c for c in candidates if c["label"].lower() not in asked_labels]
        if not pool:
            pool = candidates
        if not pool:
            return AgentResult(
                agent=self.name,
                status="error",
                result={"reason": "no competencies available; run extraction first"},
            )

        pool.sort(key=score, reverse=True)
        top = pool[: max(3, len(pool) // 4)]
        pick = rng.choice(top)

        lead = _ROLE_LEAD_IN.get(goal_type or "", "")
        template = _template_for(pick["kind"], difficulty)
        base_question = (lead + template.format(label=pick["label"])).strip()
        base_question = base_question[0].upper() + base_question[1:]

        # Optional LLM rephrase. The deterministic question above is the
        # fallback — if the LLM errors or isn't configured, we return it as-is.
        llm_provider: LLMProvider | None = tools.get("llm_provider")
        llm_model: str = tools.get("llm_model") or ""
        grounding_text: str = tools.get("grounding_text") or ""
        question = base_question
        llm_source = "template"
        if llm_provider is not None and getattr(llm_provider, "name", "mock") != "mock":
            llm_question = await _llm_rephrase_question(
                llm_provider,
                llm_model,
                base_question=base_question,
                label=pick["label"],
                difficulty=difficulty,
                goal_type=goal_type,
                grounding_text=grounding_text,
            )
            if llm_question:
                question = llm_question
                llm_source = llm_provider.name

        grounding = {
            "competency_id": pick.get("id"),
            "competency_kind": pick["kind"],
            "competency_label": pick["label"],
            "source_document_id": pick.get("source_document_id"),
            "source_chunk_ordinal": pick.get("source_chunk_ordinal"),
        }

        return AgentResult(
            agent=self.name,
            status="success",
            confidence=float(pick.get("confidence", 0.6)),
            result={
                "question": question,
                "topic": pick["label"],
                "difficulty": difficulty,
                "competency_id": pick.get("id"),
                "grounding": grounding,
                "question_source": llm_source,
            },
        )


_SYSTEM_INTERVIEWER = (
    "You are a professional interviewer. You ask ONE question at a time in "
    "natural, spoken English — no preamble, no filler, no multiple questions. "
    "Keep the question under 32 words. Do not add context, do not quote the "
    "topic back verbatim, do not change the difficulty."
)


async def _llm_rephrase_question(
    provider: LLMProvider,
    model: str,
    *,
    base_question: str,
    label: str,
    difficulty: int,
    goal_type: str | None,
    grounding_text: str,
) -> str | None:
    """Ask the LLM to rephrase the templated question. Returns None on any
    error so the caller falls back to the template."""
    role = (goal_type or "job_interview").replace("_", " ")
    prompt = (
        f"Context: this is a {role} drill at difficulty level {difficulty} "
        "(1=recall, 6=adversarial follow-up).\n"
        f"Topic the candidate must demonstrate understanding of: {label}\n"
        + (
            f"Source material the candidate wrote about this topic (ground "
            f"the question in it, do not quote verbatim):\n{grounding_text[:800]}\n"
            if grounding_text
            else ""
        )
        + f'\nOur working draft of the question: "{base_question}"\n\n'
        "Rewrite that question so it sounds like a real interviewer. Reply "
        "with ONLY the rewritten question, no preamble."
    )
    try:
        resp = await provider.generate(
            GenerationRequest(
                model=model or "gpt-4o-mini",
                prompt=prompt,
                system=_SYSTEM_INTERVIEWER,
                max_tokens=120,
                temperature=0.6,
            )
        )
    except Exception as exc:
        logger.warning("Examiner LLM rephrase failed: %s", exc)
        return None
    text = (resp.text or "").strip().strip('"').strip("'")
    if not text:
        return None
    return text
