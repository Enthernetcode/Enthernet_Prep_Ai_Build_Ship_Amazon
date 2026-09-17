from __future__ import annotations

import math

import pytest

from app.providers import (
    EmbeddingRequest,
    GenerationRequest,
    get_embedding_provider,
    get_llm_provider,
)


@pytest.mark.asyncio
async def test_mock_embedding_is_deterministic() -> None:
    provider = get_embedding_provider()
    r1 = await provider.embed(EmbeddingRequest(model="mock", texts=["hello"]))
    r2 = await provider.embed(EmbeddingRequest(model="mock", texts=["hello"]))
    assert r1.vectors == r2.vectors


@pytest.mark.asyncio
async def test_mock_embedding_dimensions_and_unit_length() -> None:
    provider = get_embedding_provider()
    resp = await provider.embed(EmbeddingRequest(model="mock", texts=["one", "two", "three"]))
    assert len(resp.vectors) == 3
    for vec in resp.vectors:
        assert len(vec) == provider.dimensions
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert math.isclose(magnitude, 1.0, abs_tol=1e-6)


@pytest.mark.asyncio
async def test_mock_embedding_differs_across_inputs() -> None:
    provider = get_embedding_provider()
    resp = await provider.embed(EmbeddingRequest(model="mock", texts=["kubernetes", "postgres"]))
    assert resp.vectors[0] != resp.vectors[1]


@pytest.mark.asyncio
async def test_mock_llm_generates_deterministic_reply() -> None:
    provider = get_llm_provider()
    a = await provider.generate(GenerationRequest(model="mock", prompt="hello world"))
    b = await provider.generate(GenerationRequest(model="mock", prompt="hello world"))
    assert a.text == b.text
    assert "mock:" in a.text
