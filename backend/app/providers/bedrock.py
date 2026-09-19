"""Amazon Bedrock provider — AWS Builder mini-challenge integration.

Two provider classes both talk to `bedrock-runtime`:

- `BedrockLLMProvider` uses the Converse API (works across Anthropic, Meta,
  Amazon Titan, Mistral, Cohere models exposed on Bedrock).
- `BedrockEmbeddingProvider` uses `invoke_model` with Titan Embed or Cohere
  Embed depending on the configured model id.

Config-driven; no per-model branching in the caller. Enable with:

    LLM_PROVIDER=bedrock
    LLM_MODEL=us.anthropic.claude-3-5-sonnet-20241022-v2:0
    EMBEDDING_PROVIDER=bedrock
    EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
    AWS_BEDROCK_REGION=us-east-1
"""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache

import boto3

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
def _bedrock_runtime():
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_bedrock_region or "us-east-1",
    )


class BedrockLLMProvider(LLMProvider):
    """Bedrock LLM via the Converse API — works with Anthropic / Meta / Titan / Mistral / Cohere."""

    name = "bedrock"

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        def _call() -> dict:
            messages = [
                {
                    "role": "user",
                    "content": [{"text": request.prompt}],
                }
            ]
            kwargs = {
                "modelId": request.model,
                "messages": messages,
            }
            if request.system:
                kwargs["system"] = [{"text": request.system}]
            inference: dict = {}
            if request.max_tokens is not None:
                inference["maxTokens"] = request.max_tokens
            if request.temperature is not None:
                inference["temperature"] = request.temperature
            if inference:
                kwargs["inferenceConfig"] = inference
            return _bedrock_runtime().converse(**kwargs)

        resp = await asyncio.to_thread(_call)
        content_blocks = (
            resp.get("output", {}).get("message", {}).get("content", []) or []
        )
        text = "".join(block.get("text", "") for block in content_blocks)
        usage = resp.get("usage", {}) or {}
        return GenerationResponse(
            text=text,
            model=request.model,
            tokens_input=usage.get("inputTokens"),
            tokens_output=usage.get("outputTokens"),
            finish_reason=resp.get("stopReason"),
            raw={"stopReason": resp.get("stopReason")},
        )


class BedrockEmbeddingProvider(EmbeddingProvider):
    """Bedrock embeddings via `invoke_model` (Titan Embed v2 default).

    Cohere Embed models are auto-detected by model id prefix; anything else
    is treated as Titan-shaped input.
    """

    name = "bedrock"

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model
        is_cohere = model.startswith("cohere.")

        def _one(text: str) -> list[float]:
            if is_cohere:
                body = json.dumps(
                    {"texts": [text], "input_type": "search_document"}
                )
                resp = _bedrock_runtime().invoke_model(
                    modelId=model,
                    body=body,
                    contentType="application/json",
                    accept="application/json",
                )
                payload = json.loads(resp["body"].read())
                return payload["embeddings"][0]
            # Titan Embed shape.
            body_dict: dict = {"inputText": text}
            if self.dimensions:
                body_dict["dimensions"] = self.dimensions
                body_dict["normalize"] = True
            resp = _bedrock_runtime().invoke_model(
                modelId=model,
                body=json.dumps(body_dict),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(resp["body"].read())
            return payload["embedding"]

        def _all() -> list[list[float]]:
            return [_one(t) for t in request.texts]

        vectors = await asyncio.to_thread(_all)
        return EmbeddingResponse(model=model, vectors=vectors, tokens=None)
