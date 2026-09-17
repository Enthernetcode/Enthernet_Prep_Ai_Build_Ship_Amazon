from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReadinessSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    session_id: uuid.UUID | None
    source: str
    overall: float
    knowledge: float
    communication: float
    evidence: float
    conciseness: float
    pressure: float
    consistency: float
    coverage: float
    detail: dict[str, Any] | None
    created_at: datetime
