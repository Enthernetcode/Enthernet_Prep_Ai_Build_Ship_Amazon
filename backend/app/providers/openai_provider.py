from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings
from app.providers.base import (
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResponse,
    GenerationRequest,
    GenerationResponse,
    LLMProvider,
)


@lru_cache
def _client() -> AsyncOpenAI:
    kwargs: dict = {"api_key": settings.openai_api_key or None}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**kwargs)


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        messages: list[dict] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        resp = await _client().chat.completions.create(
            model=request.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return GenerationResponse(
            text=choice.message.content or "",
            model=resp.model,
            tokens_input=getattr(usage, "prompt_tokens", None),
            tokens_output=getattr(usage, "completion_tokens", None),
            finish_reason=choice.finish_reason,
        )


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        resp = await _client().embeddings.create(
            model=request.model,
            input=request.texts,
            dimensions=self.dimensions,
        )
        return EmbeddingResponse(
            model=resp.model,
            vectors=[d.embedding for d in resp.data],
            tokens=getattr(resp.usage, "total_tokens", None),
        )
