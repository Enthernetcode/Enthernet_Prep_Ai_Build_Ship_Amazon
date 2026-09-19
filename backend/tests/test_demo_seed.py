from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_seed_returns_ready_to_use_bundle(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    resp = await client.post(
        "/api/v1/demo/seed",
        json={"email": "seed-a@example.com", "password": "seed-password-2026"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["dashboard_path"].startswith("/projects/")
    assert body["competencies"] > 5
    assert 0.0 <= body["baseline_readiness"] <= 0.6

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    project_id = body["project_id"]

    comps = await client.get(
        f"/api/v1/projects/{project_id}/competencies/", headers=headers
    )
    assert comps.status_code == 200
    labels = {c["label"] for c in comps.json() if c["kind"] == "technology"}
    # Both CV and JD name these, so extraction must catch them.
    assert "kubernetes" in labels
    assert "aws" in labels
    assert "terraform" in labels

    readiness = await client.get(
        f"/api/v1/projects/{project_id}/readiness/", headers=headers
    )
    assert readiness.status_code == 200
    assert readiness.json()["source"] == "baseline"


@pytest.mark.asyncio
async def test_seed_is_idempotent(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    email = "seed-idempotent@example.com"
    first = await client.post(
        "/api/v1/demo/seed", json={"email": email, "password": "seed-password-2026"}
    )
    second = await client.post(
        "/api/v1/demo/seed", json={"email": email, "password": "seed-password-2026"}
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["project_id"] == second.json()["project_id"]
    assert first.json()["user_id"] == second.json()["user_id"]


@pytest.mark.asyncio
async def test_seed_returns_404_in_production(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    resp = await client.post("/api/v1/demo/seed", json={})
    assert resp.status_code == 404
