from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    user_id: str
    project_id: str
    session_id: str | None = None
    goal_type: str | None = None
    current_topic: str | None = None
    difficulty: int | None = None
    readiness_score: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    agent: str
    status: Literal["success", "error", "partial"]
    confidence: float | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Agent(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        raise NotImplementedError
