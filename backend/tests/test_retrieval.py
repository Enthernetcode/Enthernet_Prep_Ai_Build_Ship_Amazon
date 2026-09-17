from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "hunter2hunter2"}
    )
    return resp.json()["access_token"]


async def _make_project(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "P", "goal_type": "job_interview"},
    )
    return resp.json()["id"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _wait_processed(client: AsyncClient, token: str, doc_id: str) -> None:
    for _ in range(80):
        resp = await client.get(f"/api/v1/documents/{doc_id}", headers=_hdr(token))
        body = resp.json()
        if body["status"] == "processed":
            return
        if body["status"] == "failed":
            raise AssertionError(f"processing failed: {body.get('error')}")
        await asyncio.sleep(0.1)
    raise AssertionError("timed out waiting for processed")


async def _upload_text(client: AsyncClient, token: str, project_id: str, text: str, name: str = "notes.txt") -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]
    await _wait_processed(client, token, doc_id)
    return doc_id


@pytest.mark.asyncio
async def test_retrieval_returns_matches_scoped_to_project(client: AsyncClient) -> None:
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    await _upload_text(
        client,
        token,
        project_id,
        "Kubernetes networking uses CNI plugins for pod-level connectivity.\n\n"
        "PostgreSQL replication supports both streaming and logical modes.",
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/retrieve/",
        headers=_hdr(token),
        json={"query": "any question", "k": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "any question"
    assert body["k"] == 5
    assert len(body["matches"]) >= 1
    top = body["matches"][0]
    assert "chunk_id" in top
    assert top["document_filename"] == "notes.txt"
    assert -1.0 <= top["score"] <= 1.0


@pytest.mark.asyncio
async def test_retrieval_isolated_across_projects(client: AsyncClient) -> None:
    """§21 — retrieval must not cross project boundaries."""
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_a = await _make_project(client, token)
    project_b = await _make_project(client, token)

    await _upload_text(client, token, project_a, "SECRET DATA in project A")

    resp = await client.post(
        f"/api/v1/projects/{project_b}/retrieve/",
        headers=_hdr(token),
        json={"query": "SECRET DATA"},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


@pytest.mark.asyncio
async def test_retrieval_cross_user_forbidden(client: AsyncClient) -> None:
    """§16 — user B cannot retrieve from user A's project."""
    token_a = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    token_b = await _register_login(client, f"b-{uuid.uuid4().hex[:8]}@example.com")
    project_a = await _make_project(client, token_a)
    await _upload_text(client, token_a, project_a, "A's private data")

    resp = await client.post(
        f"/api/v1/projects/{project_a}/retrieve/",
        headers=_hdr(token_b),
        json={"query": "A's private data"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retrieval_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/projects/{uuid.uuid4()}/retrieve/",
        json={"query": "test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_retrieval_returns_stable_ordering_for_same_query(client: AsyncClient) -> None:
    """Two chunks embedded by deterministic mock provider — same query returns same order."""
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    await _upload_text(
        client,
        token,
        project_id,
        "First paragraph about kubernetes.\n\nSecond paragraph about postgres.",
    )

    r1 = await client.post(
        f"/api/v1/projects/{project_id}/retrieve/", headers=_hdr(token), json={"query": "test"}
    )
    r2 = await client.post(
        f"/api/v1/projects/{project_id}/retrieve/", headers=_hdr(token), json={"query": "test"}
    )
    ids1 = [m["chunk_id"] for m in r1.json()["matches"]]
    ids2 = [m["chunk_id"] for m in r2.json()["matches"]]
    assert ids1 == ids2
