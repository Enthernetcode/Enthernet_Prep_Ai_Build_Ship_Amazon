from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    k: int | None = Field(default=None, ge=1, le=50)


class RetrievalMatch(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    ordinal: int
    text: str
    score: float
    char_start: int
    char_end: int


class RetrievalResponse(BaseModel):
    query: str
    k: int
    matches: list[RetrievalMatch]
