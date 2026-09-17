from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error: str | None = None
    created_at: datetime


class DocumentDownloadResponse(BaseModel):
    url: str
    expires_in_seconds: int
