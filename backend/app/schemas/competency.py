from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompetencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    label: str
    detail: str | None
    source_document_id: uuid.UUID | None
    source_chunk_ordinal: int | None
    confidence: float
    mastery: float
    attempts: int
    correct: int
    provenance: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class CompetencyExtractResponse(BaseModel):
    project_id: uuid.UUID
    extracted: int
    kept: int
    total: int
    kinds: dict[str, int] = Field(default_factory=dict)
