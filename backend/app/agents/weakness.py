from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult


_DIMENSION_MAP = {
    "accuracy": "knowledge",
    "completeness": "knowledge",
    "relevance": "knowledge",
    "evidence": "evidence",
    "communication": "communication",
    "conciseness": "communication",
    "response_time": "pressure",
}


class WeaknessAgent(Agent):
    """§16 Weakness Agent — turns per-dimension scores into weakness deltas.

    Returns update instructions the API layer applies to WeaknessRecord rows.
    Severity is an EMA of (1 - score) across attempts.
    """

    name = "weakness"
    description = "Convert evaluation dimensions into weakness updates."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        dims: dict[str, float] = tools["dimensions"]
        current: dict[str, float] = tools.get("current_severity", {})
        threshold: float = float(tools.get("threshold", 0.6))
        alpha: float = 0.4

        updates: list[dict[str, Any]] = []
        for raw_dim, score in dims.items():
            bucket = _DIMENSION_MAP.get(raw_dim)
            if bucket is None:
                continue
            observed = max(0.0, 1.0 - float(score))
            prev = current.get(bucket, 0.0)
            new_sev = round((1 - alpha) * prev + alpha * observed, 4)
            incremented = score < threshold
            updates.append(
                {
                    "dimension": bucket,
                    "severity": new_sev,
                    "increment_occurrence": incremented,
                }
            )

        # Collapse to one row per dimension (max severity wins if duplicates).
        collapsed: dict[str, dict[str, Any]] = {}
        for u in updates:
            existing = collapsed.get(u["dimension"])
            if existing is None or u["severity"] > existing["severity"]:
                collapsed[u["dimension"]] = u
            else:
                existing["increment_occurrence"] = (
                    existing["increment_occurrence"] or u["increment_occurrence"]
                )

        return AgentResult(
            agent=self.name,
            status="success",
            confidence=1.0,
            result={"updates": list(collapsed.values())},
        )
