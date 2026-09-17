from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient


PASSWORD = "hunter2hunter2"


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return resp.json()["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_project(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        headers=_hdr(token),
        json={"name": "Cloud Engineer", "goal_type": "job_interview"},
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
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]
    for _ in range(80):
        r = await client.get(f"/api/v1/documents/{doc_id}", headers=_hdr(token))
        body = r.json()
        if body["status"] == "processed":
            return
        if body["status"] == "failed":
            raise AssertionError(body.get("error"))
        await asyncio.sleep(0.1)
    raise AssertionError("timed out waiting for processed")


@pytest.mark.asyncio
async def test_extract_then_list_competencies_and_baseline_readiness(client: AsyncClient) -> None:
    token = await _register_login(client, f"c-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)

    await _upload_and_wait(
        client, token, project_id,
        "Senior Cloud Engineer with 6 years experience. "
        "Built platforms on AWS with Kubernetes and Terraform. "
        "Reduced p99 latency by 40% and cut infra spend 25%.",
        "cv.txt",
    )
    await _upload_and_wait(
        client, token, project_id,
        "We're hiring a Cloud Engineer proficient in AWS, Kubernetes, PostgreSQL, "
        "and Prometheus. You will own our CI/CD pipeline on GitHub.",
        "jd.txt",
    )

    extract = await client.post(
        f"/api/v1/projects/{project_id}/competencies/extract",
        headers=_hdr(token),
    )
    assert extract.status_code == 200, extract.text
    body = extract.json()
    assert body["total"] > 0
    assert body["kinds"].get("technology", 0) >= 3

    listing = await client.get(
        f"/api/v1/projects/{project_id}/competencies/", headers=_hdr(token)
    )
    assert listing.status_code == 200
    comps = listing.json()
    labels = {c["label"] for c in comps if c["kind"] == "technology"}
    assert "aws" in labels
    assert "kubernetes" in labels

    baseline = await client.post(
        f"/api/v1/projects/{project_id}/readiness/baseline", headers=_hdr(token)
    )
    assert baseline.status_code == 201, baseline.text
    scores = baseline.json()
    assert scores["source"] == "baseline"
    assert 0.0 <= scores["overall"] <= 0.6
    assert scores["coverage"] == 0.0


@pytest.mark.asyncio
async def test_extract_rejects_project_with_no_docs(client: AsyncClient) -> None:
    token = await _register_login(client, f"c-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/competencies/extract", headers=_hdr(token)
    )
    assert resp.status_code == 409
