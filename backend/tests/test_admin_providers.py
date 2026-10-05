from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import settings


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


@pytest.mark.asyncio
async def test_non_admin_gets_403(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_emails", ["admin@example.com"])
    token = await _register_login(client, f"nope-{uuid.uuid4().hex[:8]}@example.com")
    resp = await client.get("/api/v1/admin/providers", headers=_hdr(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_both_scopes(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    resp = await client.get("/api/v1/admin/providers", headers=_hdr(token))
    assert resp.status_code == 200
    scopes = {c["scope"] for c in resp.json()}
    assert scopes == {"lab", "judged"}


@pytest.mark.asyncio
async def test_admin_can_update_lab_only(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    put = await client.put(
        "/api/v1/admin/providers/lab",
        headers=_hdr(token),
        json={
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["llm_provider"] == "openai"

    # Persistence: fresh GET returns the new values.
    fresh = await client.get("/api/v1/admin/providers/lab", headers=_hdr(token))
    assert fresh.json()["llm_provider"] == "openai"

    # Judged is read-only.
    denied = await client.put(
        "/api/v1/admin/providers/judged",
        headers=_hdr(token),
        json={
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
        },
    )
    assert denied.status_code == 404

    # Restore lab to the mock default so subsequent tests aren't disturbed.
    await client.put(
        "/api/v1/admin/providers/lab",
        headers=_hdr(token),
        json={
            "llm_provider": "mock",
            "llm_model": "gpt-4o-mini",
            "embedding_provider": "mock",
            "embedding_model": "text-embedding-3-small",
        },
    )


@pytest.mark.asyncio
async def test_me_returns_is_admin(client: AsyncClient, monkeypatch) -> None:
    admin_email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    other_email = f"o-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])

    admin_token = await _register_login(client, admin_email)
    other_token = await _register_login(client, other_email)

    admin_me = await client.get("/api/v1/auth/me", headers=_hdr(admin_token))
    other_me = await client.get("/api/v1/auth/me", headers=_hdr(other_token))
    assert admin_me.json()["is_admin"] is True
    assert other_me.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_admin_rejects_unknown_provider(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    resp = await client.put(
        "/api/v1/admin/providers/lab",
        headers=_hdr(token),
        json={
            "llm_provider": "gemini-super",  # not on the allowlist
            "llm_model": "x",
            "embedding_provider": "mock",
            "embedding_model": "y",
        },
    )
    assert resp.status_code == 422
