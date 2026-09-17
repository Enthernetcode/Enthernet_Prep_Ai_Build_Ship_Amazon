from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult


_HINT_TEMPLATES = {
    "knowledge": "Start with a one-sentence definition of {topic}, then give one concrete example you have used or read about.",
    "communication": "Structure your answer as: situation, decision, outcome. Aim for 3-5 sentences.",
    "evidence": "Ground the claim with a number or a specific incident — 'reduced X by Y in Z weeks'.",
    "pressure": "Take a breath. It's OK to say 'let me think for two seconds' before answering.",
}


class CoachAgent(Agent):
    """§14 Coach Agent. Emits a short, actionable hint. Disabled in Final Boss."""

    name = "coach"
    description = "Give the user a concrete hint or structure to improve."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        mode = tools.get("mode", "mock_interview")
        if mode == "final_boss":
            return AgentResult(
                agent=self.name,
                status="success",
                confidence=1.0,
                result={"note": None, "disabled": True},
            )
        weakest = tools.get("weakest_dimension", "knowledge")
        topic = tools.get("topic", "the topic")
        template = _HINT_TEMPLATES.get(weakest, _HINT_TEMPLATES["knowledge"])
        return AgentResult(
            agent=self.name,
            status="success",
            confidence=1.0,
            result={"note": template.format(topic=topic), "disabled": False},
        )
