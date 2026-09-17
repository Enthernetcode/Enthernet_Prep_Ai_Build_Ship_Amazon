from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):
    model: str
    prompt: str
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    text: str
    model: str
    tokens_input: int | None = None
    tokens_output: int | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError


class EmbeddingRequest(BaseModel):
    model: str
    texts: list[str]


class EmbeddingResponse(BaseModel):
    model: str
    vectors: list[list[float]]
    tokens: int | None = None


class EmbeddingProvider(ABC):
    name: str
    dimensions: int

    @abstractmethod
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError
