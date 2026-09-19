from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _reset_provider_caches():
    """Providers are cached at module load. Clear them so per-test settings
    monkeypatching actually picks a fresh instance each time."""
    from app.providers import get_embedding_provider, get_llm_provider
    from app.providers import openai_provider

    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    openai_provider._client.cache_clear()
    yield
    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    openai_provider._client.cache_clear()


def _fake_llm_response() -> SimpleNamespace:
    """Mimic openai>=1.x chat.completions response shape."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="mocked reply"),
                finish_reason="stop",
            )
        ],
        model="gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )


def _fake_embedding_response(dim: int, count: int) -> SimpleNamespace:
    return SimpleNamespace(
        model="text-embedding-3-small",
        data=[SimpleNamespace(embedding=[0.01 * i] * dim) for i in range(count)],
        usage=SimpleNamespace(total_tokens=42),
    )


def _install_mock_client(monkeypatch, *, dim: int, embed_count: int = 1) -> MagicMock:
    from app.providers import openai_provider

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_fake_llm_response())
    client.embeddings.create = AsyncMock(
        return_value=_fake_embedding_response(dim, embed_count)
    )
    monkeypatch.setattr(openai_provider, "_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_openai_llm_provider_wraps_sdk_response(monkeypatch) -> None:
    from app.providers.base import GenerationRequest
    from app.providers.openai_provider import OpenAILLMProvider

    client = _install_mock_client(monkeypatch, dim=settings.embedding_dimensions)
    resp = await OpenAILLMProvider().generate(
        GenerationRequest(
            model="gpt-4o-mini",
            prompt="hello",
            system="you are a test",
            max_tokens=32,
            temperature=0.2,
        )
    )
    assert resp.text == "mocked reply"
    assert resp.model == "gpt-4o-mini"
    assert resp.tokens_input == 12
    assert resp.tokens_output == 4
    assert resp.finish_reason == "stop"

    call = client.chat.completions.create.await_args
    assert call.kwargs["model"] == "gpt-4o-mini"
    messages = call.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "you are a test"}
    assert messages[1] == {"role": "user", "content": "hello"}
    assert call.kwargs["max_tokens"] == 32
    assert call.kwargs["temperature"] == 0.2


@pytest.mark.asyncio
async def test_openai_embedding_provider_wraps_sdk_response(monkeypatch) -> None:
    from app.providers.base import EmbeddingRequest
    from app.providers.openai_provider import OpenAIEmbeddingProvider

    dim = settings.embedding_dimensions
    client = _install_mock_client(monkeypatch, dim=dim, embed_count=3)
    resp = await OpenAIEmbeddingProvider(dimensions=dim).embed(
        EmbeddingRequest(model="text-embedding-3-small", texts=["a", "b", "c"])
    )
    assert resp.model == "text-embedding-3-small"
    assert len(resp.vectors) == 3
    for vec in resp.vectors:
        assert len(vec) == dim
    assert resp.tokens == 42

    call = client.embeddings.create.await_args
    assert call.kwargs["input"] == ["a", "b", "c"]
    assert call.kwargs["dimensions"] == dim


@pytest.mark.asyncio
async def test_provider_factory_switches_on_setting(monkeypatch) -> None:
    from app.providers import get_embedding_provider, get_llm_provider
    from app.providers.openai_provider import OpenAIEmbeddingProvider, OpenAILLMProvider

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-a-real-key")

    llm = get_llm_provider()
    emb = get_embedding_provider()
    assert isinstance(llm, OpenAILLMProvider)
    assert isinstance(emb, OpenAIEmbeddingProvider)
    assert emb.dimensions == settings.embedding_dimensions


@pytest.mark.asyncio
async def test_openai_embedding_end_to_end_via_factory(monkeypatch) -> None:
    """Prove the OpenAI provider works through the same factory the ingest
    pipeline uses — this is the code path that runs in production."""
    from app.providers import EmbeddingRequest, get_embedding_provider

    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    _install_mock_client(monkeypatch, dim=settings.embedding_dimensions, embed_count=2)

    provider = get_embedding_provider()
    resp = await provider.embed(
        EmbeddingRequest(model=settings.embedding_model, texts=["alpha", "beta"])
    )
    assert len(resp.vectors) == 2
    assert all(len(v) == settings.embedding_dimensions for v in resp.vectors)
