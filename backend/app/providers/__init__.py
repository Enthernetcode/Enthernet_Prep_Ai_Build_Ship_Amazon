from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.providers.base import (
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResponse,
    GenerationRequest,
    GenerationResponse,
    LLMProvider,
)
from app.providers.mock import MockEmbeddingProvider, MockLLMProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "GenerationRequest",
    "GenerationResponse",
    "LLMProvider",
    "get_llm_provider",
    "get_embedding_provider",
]


@lru_cache
def get_llm_provider() -> LLMProvider:
    kind = settings.llm_provider.lower()
    if kind == "mock":
        return MockLLMProvider()
    if kind == "openai":
        from app.providers.openai_provider import OpenAILLMProvider

        return OpenAILLMProvider()
    raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r}")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    kind = settings.embedding_provider.lower()
    if kind == "mock":
        return MockEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if kind == "openai":
        from app.providers.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(dimensions=settings.embedding_dimensions)
    raise ValueError(f"Unknown embedding_provider: {settings.embedding_provider!r}")
