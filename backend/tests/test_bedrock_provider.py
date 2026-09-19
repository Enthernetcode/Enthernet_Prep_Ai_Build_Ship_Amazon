from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _reset_caches():
    from app.providers import get_embedding_provider, get_llm_provider
    from app.providers import bedrock

    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    bedrock._bedrock_runtime.cache_clear()
    yield
    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    bedrock._bedrock_runtime.cache_clear()


@pytest.mark.asyncio
async def test_bedrock_llm_wraps_converse_response(monkeypatch) -> None:
    from app.providers import bedrock
    from app.providers.base import GenerationRequest
    from app.providers.bedrock import BedrockLLMProvider

    client = MagicMock()
    client.converse.return_value = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "hello from bedrock"}],
            }
        },
        "usage": {"inputTokens": 10, "outputTokens": 3},
        "stopReason": "end_turn",
    }
    monkeypatch.setattr(bedrock, "_bedrock_runtime", lambda: client)

    resp = await BedrockLLMProvider().generate(
        GenerationRequest(
            model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            prompt="say hi",
            system="you are terse",
            max_tokens=32,
            temperature=0.1,
        )
    )
    assert resp.text == "hello from bedrock"
    assert resp.tokens_input == 10
    assert resp.tokens_output == 3
    assert resp.finish_reason == "end_turn"

    call = client.converse.call_args
    assert call.kwargs["modelId"].startswith("us.anthropic.claude")
    assert call.kwargs["system"] == [{"text": "you are terse"}]
    assert call.kwargs["messages"][0]["role"] == "user"
    assert call.kwargs["inferenceConfig"] == {"maxTokens": 32, "temperature": 0.1}


@pytest.mark.asyncio
async def test_bedrock_titan_embedding_wraps_invoke_model(monkeypatch) -> None:
    from app.providers import bedrock
    from app.providers.base import EmbeddingRequest
    from app.providers.bedrock import BedrockEmbeddingProvider

    client = MagicMock()
    dim = settings.embedding_dimensions

    def _fresh_response(*args, **kwargs):
        return {
            "body": io.BytesIO(json.dumps({"embedding": [0.01] * dim}).encode())
        }

    client.invoke_model.side_effect = _fresh_response
    monkeypatch.setattr(bedrock, "_bedrock_runtime", lambda: client)

    resp = await BedrockEmbeddingProvider(dimensions=dim).embed(
        EmbeddingRequest(model="amazon.titan-embed-text-v2:0", texts=["a", "b"])
    )
    assert len(resp.vectors) == 2
    assert len(resp.vectors[0]) == dim
    # First call — inspect the body sent.
    first_call = client.invoke_model.call_args_list[0]
    sent = json.loads(first_call.kwargs["body"])
    assert sent["inputText"] == "a"
    assert sent["dimensions"] == dim
    assert sent["normalize"] is True


@pytest.mark.asyncio
async def test_bedrock_cohere_embedding_uses_cohere_body(monkeypatch) -> None:
    from app.providers import bedrock
    from app.providers.base import EmbeddingRequest
    from app.providers.bedrock import BedrockEmbeddingProvider

    client = MagicMock()
    body_bytes = json.dumps({"embeddings": [[0.5] * 8]}).encode()
    client.invoke_model.return_value = {"body": io.BytesIO(body_bytes)}
    monkeypatch.setattr(bedrock, "_bedrock_runtime", lambda: client)

    resp = await BedrockEmbeddingProvider(dimensions=8).embed(
        EmbeddingRequest(model="cohere.embed-english-v3", texts=["hi"])
    )
    assert resp.vectors == [[0.5] * 8]
    sent = json.loads(client.invoke_model.call_args.kwargs["body"])
    assert sent["texts"] == ["hi"]
    assert sent["input_type"] == "search_document"


@pytest.mark.asyncio
async def test_factory_returns_bedrock_when_configured(monkeypatch) -> None:
    from app.providers import get_embedding_provider, get_llm_provider
    from app.providers.bedrock import BedrockEmbeddingProvider, BedrockLLMProvider

    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "embedding_provider", "bedrock")
    monkeypatch.setattr(settings, "aws_bedrock_region", "us-east-1")

    assert isinstance(get_llm_provider(), BedrockLLMProvider)
    assert isinstance(get_embedding_provider(), BedrockEmbeddingProvider)
