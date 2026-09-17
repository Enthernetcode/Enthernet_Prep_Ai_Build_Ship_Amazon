from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me_flow(client: AsyncClient, unique_email: str) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "hunter2hunter2"},
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["email"] == unique_email

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "hunter2hunter2"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert token

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == unique_email


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client: AsyncClient, unique_email: str) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "hunter2hunter2"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "wrong-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(client: AsyncClient, unique_email: str) -> None:
    body = {"email": unique_email, "password": "hunter2hunter2"}
    first = await client.post("/api/v1/auth/register", json=body)
    assert first.status_code == 201
    dup = await client.post("/api/v1/auth/register", json=body)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
