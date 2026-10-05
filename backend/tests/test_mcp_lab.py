from __future__ import annotations

import json
import uuid
from typing import Any

import httpx2
import pytest
from httpx import AsyncClient
from httpx2 import ASGITransport

from app.config import settings
from app.main import app as fastapi_app


PASSWORD = "hunter2hunter2"


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return resp.json()["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_mcp_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=ASGITransport(app=fastapi_app))


async def http_call(
    token: str,
    method: str,
    params: dict[str, Any] | None = None,
    endpoint: str = "http://test/api/v1/mcp-lab/",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async with _make_mcp_client() as hc:
        init_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if extra_headers:
            init_headers.update(extra_headers)
        init = await hc.post(
            endpoint,
            headers=init_headers,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        session_id = init.headers.get("mcp-session-id")
        headers = dict(init_headers)
        if session_id:
            headers["mcp-session-id"] = session_id
        await hc.post(
            endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        resp = await hc.post(
            endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or {},
            },
        )
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    return json.loads(resp.text)


def _tool_result(body: dict[str, Any]) -> Any:
    assert "error" not in body, body
    result = body["result"]
    if result.get("structuredContent"):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except json.JSONDecodeError:
                return block["text"]
    return result


@pytest.mark.asyncio
async def test_lab_lists_expected_tools(client: AsyncClient) -> None:
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    body = await http_call(token, "tools/list")
    names = {t["name"] for t in body["result"]["tools"]}
    # All 7 judged tools present.
    for expected in (
        "prep.list_projects",
        "prep.extract_competencies",
        "prep.get_readiness",
        "prep.start_session",
        "prep.next_question",
        "prep.submit_answer",
        "prep.finish_session",
    ):
        assert expected in names
    # Plus the lab-only diagnostic.
    assert "prep.debug.resolve_provider" in names


@pytest.mark.asyncio
async def test_resolver_defaults_to_db_value(client: AsyncClient) -> None:
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    body = await http_call(
        token,
        "tools/call",
        {"name": "prep.debug.resolve_provider", "arguments": {}},
    )
    payload = _tool_result(body)
    assert payload["llm_provider"] in {"mock", "openai", "bedrock"}
    # No header override → source is db (or settings if DB is empty for scope).
    assert payload["source"] in {"db", "settings"}


@pytest.mark.asyncio
async def test_resolver_honours_header_override(client: AsyncClient) -> None:
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    body = await http_call(
        token,
        "tools/call",
        {"name": "prep.debug.resolve_provider", "arguments": {}},
        extra_headers={"X-LLM-Provider": "openai"},
    )
    payload = _tool_result(body)
    assert payload["llm_provider"] == "openai"
    assert payload["source"] == "header"


@pytest.mark.asyncio
async def test_judged_endpoint_unchanged(client: AsyncClient) -> None:
    """Sanity — the judged endpoint at /api/v1/mcp/ still lists exactly 7 tools
    and does NOT have the lab-only diagnostic."""
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    body = await http_call(
        token, "tools/list", endpoint="http://test/api/v1/mcp/"
    )
    names = {t["name"] for t in body["result"]["tools"]}
    assert len(names) == 7
    assert "prep.debug.resolve_provider" not in names
