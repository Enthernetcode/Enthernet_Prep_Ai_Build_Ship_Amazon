from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
    b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
    b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>endobj\n"
    b"xref\n0 4\n"
    b"trailer<< /Root 1 0 R /Size 4 >>\nstartxref\n0\n%%EOF\n"
)


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "hunter2hunter2"}
    )
    return login.json()["access_token"]


async def _make_project(client: AsyncClient, token: str, name: str = "Test") -> str:
    resp = await client.post(
        "/api/v1/projects/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "goal_type": "job_interview"},
    )
    return resp.json()["id"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_list_get_download_delete(client: AsyncClient) -> None:
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    upload = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": ("cv.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()
    assert document["filename"] == "cv.pdf"
    assert document["mime_type"] == "application/pdf"
    assert document["size_bytes"] == len(MINIMAL_PDF)
    assert document["status"] == "uploaded"

    listing = await client.get(
        f"/api/v1/projects/{project_id}/documents/", headers=_hdr(token)
    )
    assert listing.status_code == 200
    assert any(d["id"] == document["id"] for d in listing.json())

    meta = await client.get(f"/api/v1/documents/{document['id']}", headers=_hdr(token))
    assert meta.status_code == 200
    assert meta.json()["id"] == document["id"]

    dl = await client.get(
        f"/api/v1/documents/{document['id']}/download", headers=_hdr(token)
    )
    assert dl.status_code == 200
    body = dl.json()
    assert body["url"].startswith("http")
    assert "X-Amz-Signature" in body["url"]
    assert body["expires_in_seconds"] > 0

    delete = await client.delete(
        f"/api/v1/documents/{document['id']}", headers=_hdr(token)
    )
    assert delete.status_code == 204

    gone = await client.get(f"/api/v1/documents/{document['id']}", headers=_hdr(token))
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_document_hidden(client: AsyncClient) -> None:
    """§16 — user B must not see or download user A's document."""
    token_a = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    token_b = await _register_login(client, f"b-{uuid.uuid4().hex[:8]}@example.com")
    project_a = await _make_project(client, token_a)

    upload = await client.post(
        f"/api/v1/projects/{project_a}/documents/",
        headers=_hdr(token_a),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    resp = await client.get(f"/api/v1/documents/{document_id}", headers=_hdr(token_b))
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/documents/{document_id}/download", headers=_hdr(token_b)
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/projects/{project_a}/documents/", headers=_hdr(token_b)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rejected_mime_type(client: AsyncClient) -> None:
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_oversized_upload_rejected(client: AsyncClient, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "document_max_size_bytes", 64)
    token = await _register_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/",
        headers=_hdr(token),
        files={"file": ("big.txt", b"x" * 200, "text/plain")},
    )
    assert resp.status_code == 413, f"got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/projects/{uuid.uuid4()}/documents/",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 401
