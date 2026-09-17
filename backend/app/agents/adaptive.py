from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult


class AdaptivePlannerAgent(Agent):
    """§17 Adaptive Planner — picks the next move based on the last evaluation
    and recent history.

    Actions: `increase_difficulty`, `follow_up`, `probe_concept`,
    `coach_intervention`, `reduce_frequency`, `finish`.
    """

    name = "adaptive"
    description = "Decide the next action after a turn."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        overall: float = float(tools["overall"])
        difficulty: int = int(tools.get("difficulty", context.difficulty or 3))
        recent_scores: list[float] = list(tools.get("recent_scores", []))
        weakness_severity: float = float(tools.get("weakness_severity", 0.0))
        mode: str = tools.get("mode", "mock_interview")
        topic: str = tools.get("topic", "")
        turns_taken: int = int(tools.get("turns_taken", 1))
        max_turns: int = int(tools.get("max_turns", 8 if mode != "final_boss" else 10))

        # Final boss and quiz never emit hints; still choose next difficulty.
        coach_note: str | None = None

        if turns_taken >= max_turns:
            action = "finish"
            next_difficulty = difficulty
        elif overall >= 0.8:
            action = "increase_difficulty"
            next_difficulty = min(6, difficulty + 1)
            if mode not in ("final_boss", "quiz"):
                coach_note = f"Strong on {topic or 'that topic'} — leveling up."
        elif overall >= 0.55:
            action = "follow_up"
            next_difficulty = difficulty
        elif overall >= 0.35:
            action = "probe_concept"
            next_difficulty = max(1, difficulty - 1)
            if mode not in ("final_boss",):
                coach_note = (
                    f"Partial answer. Anchor on the fundamentals of {topic or 'the topic'}."
                )
        else:
            # Repeated low scores → coach intervention.
            consecutive_low = 0
            for s in reversed(recent_scores):
                if s < 0.35:
                    consecutive_low += 1
                else:
                    break
            action = "coach_intervention" if consecutive_low >= 2 else "probe_concept"
            next_difficulty = max(1, difficulty - 1)
            if mode not in ("final_boss",):
                coach_note = (
                    "Let's slow down. I'll give you a scaffolded example, then retry."
                )

        # Elevated weakness severity biases toward mastery reinforcement.
        if action == "increase_difficulty" and weakness_severity > 0.7:
            action = "follow_up"
            next_difficulty = difficulty

        return AgentResult(
            agent=self.name,
            status="success",
            confidence=1.0,
            result={
                "action": action,
                "next_difficulty": next_difficulty,
                "coach_note": coach_note,
                "should_finish": action == "finish",
            },
        )
