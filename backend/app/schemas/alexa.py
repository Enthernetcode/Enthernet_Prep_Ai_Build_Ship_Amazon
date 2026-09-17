from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlexaRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0"
    session: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)


class AlexaResponse(BaseModel):
    version: str = "1.0"
    sessionAttributes: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
