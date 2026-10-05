"""Per-request provider resolver.

Used by the Lab MCP server (`/api/v1/mcp-lab/`) to pick an LLM / embedding
provider on each request. The Judged MCP server does not use this — it stays
on `settings.llm_provider` via the module-level `get_llm_provider` cache.

Resolution order (first match wins):

1. `X-LLM-Provider` request header (e.g. "openai", "bedrock", "mock").
2. `provider_configs` row for the given scope in the database.
3. `settings.llm_provider` fallback.

Returns fresh provider instances (bypasses the lru_cache in
`app/providers/__init__.py`) so per-request switching actually works.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.provider_config import ProviderConfig
from app.providers.base import EmbeddingProvider, LLMProvider
from app.providers.mock import MockEmbeddingProvider, MockLLMProvider


VALID_LLM_PROVIDERS = {"mock", "openai", "bedrock"}
VALID_EMBEDDING_PROVIDERS = {"mock", "openai", "bedrock"}


@dataclass(frozen=True)
class ResolvedProviders:
    llm_name: str
    llm_model: str
    embedding_name: str
    embedding_model: str
    source: str  # "header" | "db" | "settings"


def _extract_header(ctx: Any, name: str) -> str | None:
    headers = getattr(ctx, "headers", None)
    if not headers:
        return None
    return headers.get(name) or headers.get(name.lower())


async def _load_config(session: AsyncSession, scope: str) -> ProviderConfig | None:
    return (
        await session.execute(
            select(ProviderConfig).where(ProviderConfig.scope == scope)
        )
    ).scalar_one_or_none()


async def resolve_providers(
    ctx: Any,
    session: AsyncSession,
    scope: str = "lab",
) -> ResolvedProviders:
    """Compute the provider names + models for this request. Fresh DB read per
    call — cheap (one indexed lookup, one row) and reflects admin changes
    immediately."""
    header_llm = _extract_header(ctx, "X-LLM-Provider")
    header_emb = _extract_header(ctx, "X-Embedding-Provider")
    header_llm_model = _extract_header(ctx, "X-LLM-Model")
    header_emb_model = _extract_header(ctx, "X-Embedding-Model")

    cfg = await _load_config(session, scope)

    llm_name = _pick(header_llm, cfg.llm_provider if cfg else None, settings.llm_provider, VALID_LLM_PROVIDERS)
    emb_name = _pick(
        header_emb,
        cfg.embedding_provider if cfg else None,
        settings.embedding_provider,
        VALID_EMBEDDING_PROVIDERS,
    )
    llm_model = header_llm_model or (cfg.llm_model if cfg else None) or settings.llm_model
    emb_model = (
        header_emb_model
        or (cfg.embedding_model if cfg else None)
        or settings.embedding_model
    )

    source = "header" if (header_llm or header_emb) else ("db" if cfg else "settings")

    return ResolvedProviders(
        llm_name=llm_name,
        llm_model=llm_model,
        embedding_name=emb_name,
        embedding_model=emb_model,
        source=source,
    )


def _pick(header: str | None, db_value: str | None, fallback: str, valid: set[str]) -> str:
    for candidate in (header, db_value, fallback):
        if candidate and candidate.lower() in valid:
            return candidate.lower()
    return "mock"


def build_llm_provider(name: str) -> LLMProvider:
    """Return a fresh (uncached) LLM provider instance for `name`."""
    key = name.lower()
    if key == "mock":
        return MockLLMProvider()
    if key == "openai":
        from app.providers.openai_provider import OpenAILLMProvider

        return OpenAILLMProvider()
    if key == "bedrock":
        from app.providers.bedrock import BedrockLLMProvider

        return BedrockLLMProvider()
    raise ValueError(f"Unknown llm_provider: {name!r}")


def build_embedding_provider(name: str) -> EmbeddingProvider:
    key = name.lower()
    if key == "mock":
        return MockEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if key == "openai":
        from app.providers.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if key == "bedrock":
        from app.providers.bedrock import BedrockEmbeddingProvider

        return BedrockEmbeddingProvider(dimensions=settings.embedding_dimensions)
    raise ValueError(f"Unknown embedding_provider: {name!r}")
