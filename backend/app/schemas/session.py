from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SessionMode = Literal[
    "mock_interview",
    "weakness_drill",
    "final_boss",
    "study",
    "quiz",
]


class SessionCreate(BaseModel):
    mode: SessionMode = "mock_interview"
    difficulty: int = Field(default=3, ge=1, le=6)


class TurnAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    seconds_taken: float | None = Field(default=None, ge=0.0, le=3600.0)


class TurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    ordinal: int
    question: str
    topic: str | None
    difficulty: int
    competency_id: uuid.UUID | None
    grounding: dict[str, Any] | None
    user_answer: str | None
    evaluation: dict[str, Any] | None
    adaptive_action: dict[str, Any] | None
    coach_note: str | None
    asked_at: datetime
    answered_at: datetime | None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    mode: str
    status: str
    difficulty: int
    summary: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None


class SessionWithTurns(SessionResponse):
    turns: list[TurnResponse] = Field(default_factory=list)
