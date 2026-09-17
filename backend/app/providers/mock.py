from __future__ import annotations

import hashlib
import math
import struct

from app.providers.base import (
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResponse,
    GenerationRequest,
    GenerationResponse,
    LLMProvider,
)


def _seeded_vector(text: str, dimensions: int) -> list[float]:
    """Deterministic unit-length vector from text.

    SHA-512-seeded stream expanded to `dimensions` floats in [-1, 1], then
    L2-normalized. Same text always yields the same vector, and different
    texts yield different vectors with high probability.
    """
    seed = hashlib.sha512(text.encode("utf-8")).digest()
    buf = bytearray()
    counter = 0
    while len(buf) < dimensions * 4:
        buf.extend(hashlib.sha512(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    raw = struct.unpack(f"{dimensions}i", bytes(buf[: dimensions * 4]))
    scale = float(2**31)
    values = [x / scale for x in raw]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class MockLLMProvider(LLMProvider):
    """Deterministic offline LLM. Returns a canned reply that includes a
    fingerprint of the prompt — useful for asserting agent wiring without
    burning tokens or requiring network access."""

    name = "mock"

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        digest = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()[:12]
        text = f"[mock:{digest}] {request.prompt[:120]}"
        return GenerationResponse(
            text=text,
            model=request.model or "mock",
            tokens_input=len(request.prompt) // 4,
            tokens_output=len(text) // 4,
            finish_reason="stop",
        )


class MockEmbeddingProvider(EmbeddingProvider):
    name = "mock"

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = [_seeded_vector(t, self.dimensions) for t in request.texts]
        return EmbeddingResponse(
            model=request.model or "mock",
            vectors=vectors,
            tokens=sum(len(t) // 4 for t in request.texts),
        )
