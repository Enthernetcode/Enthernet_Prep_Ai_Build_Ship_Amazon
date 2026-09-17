from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "hunter2hunter2"}
    )
    return login.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_and_list_project(client: AsyncClient) -> None:
    token = await _register_and_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")

    create = await client.post(
        "/api/v1/projects/",
        headers=_headers(token),
        json={
            "name": "Cloud Engineer Interview",
            "goal_type": "job_interview",
            "goal_description": "Prep for a cloud engineer role",
            "target_date": "2026-10-10",
            "difficulty": 4,
        },
    )
    assert create.status_code == 201, create.text
    project = create.json()
    assert project["name"] == "Cloud Engineer Interview"
    assert project["difficulty"] == 4

    listing = await client.get("/api/v1/projects/", headers=_headers(token))
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["id"] == project["id"]


@pytest.mark.asyncio
async def test_user_isolation(client: AsyncClient) -> None:
    """§16 — user A must not see or fetch user B's projects."""
    token_a = await _register_and_login(client, f"a-{uuid.uuid4().hex[:8]}@example.com")
    token_b = await _register_and_login(client, f"b-{uuid.uuid4().hex[:8]}@example.com")

    created = await client.post(
        "/api/v1/projects/",
        headers=_headers(token_a),
        json={"name": "A's project", "goal_type": "job_interview"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    b_list = await client.get("/api/v1/projects/", headers=_headers(token_b))
    assert b_list.status_code == 200
    assert b_list.json() == []

    b_fetch = await client.get(f"/api/v1/projects/{project_id}", headers=_headers(token_b))
    assert b_fetch.status_code == 404, f"got {b_fetch.status_code}: {b_fetch.text}"


@pytest.mark.asyncio
async def test_projects_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects/")
    assert resp.status_code == 401
