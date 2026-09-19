from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx2
import pytest
from httpx import AsyncClient
from httpx2 import ASGITransport

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


async def _make_project(client: AsyncClient, token: str, name: str = "MCP P") -> str:
    resp = await client.post(
        "/api/v1/projects/",
        headers=_hdr(token),
        json={"name": name, "goal_type": "job_interview"},
    )
    return resp.json()["id"]


async def _upload_and_wait(
    client: AsyncClient, token: str, project_id: str, text: str, name: str
) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    for _ in range(80):
        r = await client.get(f"/api/v1/documents/{doc_id}", headers=_hdr(token))
        if r.json()["status"] == "processed":
            return
        await asyncio.sleep(0.1)
    raise AssertionError("timed out")


def _make_mcp_client() -> httpx2.AsyncClient:
    """MCP client that speaks to our FastAPI app in-process via ASGI."""
    return httpx2.AsyncClient(transport=ASGITransport(app=fastapi_app))


def _unwrap(result: Any) -> Any:
    """MCP tool results come back as CallToolResult with a list of Content blocks.

    The v2 SDK returns structured content in `.structuredContent` when the tool
    returns a dict, otherwise the text of the first content block.
    """
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    for block in result.content or []:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except (json.JSONDecodeError, TypeError):
                return block.text
    return None


@pytest.mark.asyncio
async def test_mcp_lists_tools(client: AsyncClient) -> None:
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    tools_resp = await http_call(client, token, {"method": "tools/list"})
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert "prep.list_projects" in tool_names
    assert "prep.start_session" in tool_names
    assert "prep.submit_answer" in tool_names
    assert "prep.finish_session" in tool_names


async def http_call(
    _client: AsyncClient, token: str, message: dict[str, Any]
) -> dict[str, Any]:
    """Directly call the mounted MCP endpoint via a fresh in-process httpx2 client.

    Returns the parsed JSON-RPC response (Streamable HTTP returns SSE — parse
    the first `data:` frame)."""
    payload = {"jsonrpc": "2.0", "id": 1, **message}
    if "params" not in payload:
        payload["params"] = {}
    async with _make_mcp_client() as hc:
        # Initialize a session first.
        init = await hc.post(
            "http://test/api/v1/mcp/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["mcp-session-id"] = session_id
        # Send the required initialized notification.
        await hc.post(
            "http://test/api/v1/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        resp = await hc.post(
            "http://test/api/v1/mcp/", headers=headers, json=payload
        )
    text = resp.text
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    return json.loads(text)


async def _call_tool(
    client: AsyncClient, token: str, name: str, arguments: dict[str, Any]
) -> Any:
    body = await http_call(
        client,
        token,
        {
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
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
async def test_mcp_full_prep_loop_over_streamable_http(client: AsyncClient) -> None:
    token = await _register_login(client, f"m-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token, name="MCP Loop Project")
    await _upload_and_wait(
        client, token, project_id,
        "Cloud Engineer built AWS Kubernetes Terraform platforms. "
        "Reduced deploy time 70%. Handles 5000 rps.",
        "cv.txt",
    )
    await _upload_and_wait(
        client, token, project_id,
        "Cloud Engineer role: AWS, Kubernetes, PostgreSQL, GitHub Actions CI/CD.",
        "jd.txt",
    )

    projects = await _call_tool(client, token, "prep.list_projects", {})
    assert any(p["id"] == project_id for p in projects["projects"])

    extract = await _call_tool(
        client, token, "prep.extract_competencies", {"project_id": project_id}
    )
    assert extract["total"] > 0
    assert 0.0 <= extract["baseline_readiness"] <= 0.6

    readiness = await _call_tool(
        client, token, "prep.get_readiness", {"project_id": project_id}
    )
    assert readiness["source"] == "baseline"

    session_start = await _call_tool(
        client,
        token,
        "prep.start_session",
        {"project_id": project_id, "mode": "mock_interview", "difficulty": 3},
    )
    session_id = session_start["session_id"]

    turn = await _call_tool(
        client, token, "prep.next_question", {"session_id": session_id}
    )
    assert turn["question"]

    answered = await _call_tool(
        client,
        token,
        "prep.submit_answer",
        {
            "session_id": session_id,
            "ordinal": turn["ordinal"],
            "answer": (
                "AWS is a public cloud. Kubernetes orchestrates containers. "
                "At my last job we used Terraform for our VPC and reduced deploy "
                "time by 70 percent by moving to Argo CD."
            ),
            "seconds_taken": 42,
        },
    )
    assert "evaluation" in answered
    assert 0.0 <= answered["evaluation"]["overall"] <= 1.0
    assert answered["adaptive_action"]["action"] in {
        "increase_difficulty", "follow_up", "probe_concept", "coach_intervention", "finish",
    }
    assert 0.0 <= answered["readiness"]["overall"] <= 1.0

    finished = await _call_tool(
        client, token, "prep.finish_session", {"session_id": session_id}
    )
    assert finished["status"] == "completed"
    assert "readiness" in finished


@pytest.mark.asyncio
async def test_mcp_rejects_missing_bearer_token(client: AsyncClient) -> None:
    async with _make_mcp_client() as hc:
        init = await hc.post(
            "http://test/api/v1/mcp/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "no-auth", "version": "1"},
                },
            },
        )
        session_id = init.headers.get("mcp-session-id")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["mcp-session-id"] = session_id
        await hc.post(
            "http://test/api/v1/mcp/",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        resp = await hc.post(
            "http://test/api/v1/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "prep.list_projects", "arguments": {}},
            },
        )
    text = resp.text
    body = None
    for line in text.splitlines():
        if line.startswith("data:"):
            body = json.loads(line[len("data:") :].strip())
            break
    assert body is not None
    # Either the RPC returns an error, or the result carries isError=True.
    if "error" in body:
        assert "Authorization" in body["error"]["message"]
    else:
        assert body["result"].get("isError") is True
