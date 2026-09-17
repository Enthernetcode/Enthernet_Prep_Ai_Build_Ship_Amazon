from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal_type: str = Field(min_length=1, max_length=64)
    goal_description: str | None = None
    target_date: date | None = None
    difficulty: int = Field(default=3, ge=1, le=6)
    evaluation_profile: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    goal_type: str
    goal_description: str | None
    target_date: date | None
    difficulty: int
    evaluation_profile: dict[str, Any] | None
    created_at: datetime
