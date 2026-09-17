from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "hunter2hunter2"}
    )
    return login.json()["access_token"]


async def _make_project(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "P", "goal_type": "job_interview"},
    )
    return resp.json()["id"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _wait_for_status(client: AsyncClient, token: str, doc_id: str, expected: str) -> dict:
    for _ in range(60):
        resp = await client.get(f"/api/v1/documents/{doc_id}", headers=_hdr(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] == expected:
            return body
        if body["status"] == "failed":
            raise AssertionError(f"document failed: {body.get('error')}")
        await asyncio.sleep(0.1)
    raise AssertionError(f"timed out waiting for status={expected}; last={body}")


@pytest.mark.asyncio
async def test_text_document_produces_chunks(client: AsyncClient) -> None:
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    body = ("Paragraph one about kubernetes.\n\n"
            "Paragraph two about networking, service meshes, and load balancers.\n\n"
            "Paragraph three about storage classes and CSI drivers.").encode()

    upload = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": ("notes.txt", body, "text/plain")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]
    assert upload.json()["status"] == "uploaded"

    processed = await _wait_for_status(client, token, doc_id, "processed")
    assert processed["error"] is None

    chunks_resp = await client.get(
        f"/api/v1/documents/{doc_id}/chunks", headers=_hdr(token)
    )
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) >= 1
    joined = " ".join(c["text"] for c in chunks)
    assert "kubernetes" in joined
    assert "networking" in joined
    assert "CSI drivers" in joined
    for i, c in enumerate(chunks):
        assert c["ordinal"] == i
        assert c["char_end"] > c["char_start"]


@pytest.mark.asyncio
async def test_chunks_isolated_across_users(client: AsyncClient) -> None:
    token_a = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    token_b = await _register_login(client, f"b-{uuid.uuid4().hex[:8]}@example.com")
    project_a = await _make_project(client, token_a)

    upload = await client.post(
        f"/api/v1/projects/{project_a}/documents/",
        headers=_hdr(token_a),
        files={"file": ("notes.txt", b"private data", "text/plain")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    await _wait_for_status(client, token_a, doc_id, "processed")

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/chunks", headers=_hdr(token_b)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chunks_require_auth(client: AsyncClient) -> None:
    resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks")
    assert resp.status_code == 401
