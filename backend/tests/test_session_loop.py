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
        json={"name": "Session P", "goal_type": "job_interview"},
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


async def _prepare_project(client: AsyncClient, token: str) -> str:
    project_id = await _make_project(client, token)
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
    resp = await client.post(
        f"/api/v1/projects/{project_id}/competencies/extract", headers=_hdr(token)
    )
    assert resp.status_code == 200
    return project_id


@pytest.mark.asyncio
async def test_full_session_loop_produces_readiness_snapshots(client: AsyncClient) -> None:
    token = await _register_login(client, f"s-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _prepare_project(client, token)

    start = await client.post(
        f"/api/v1/projects/{project_id}/sessions/",
        headers=_hdr(token),
        json={"mode": "mock_interview", "difficulty": 3},
    )
    assert start.status_code == 201, start.text
    session_id = start.json()["id"]

    turn = await client.post(f"/api/v1/sessions/{session_id}/turns", headers=_hdr(token))
    assert turn.status_code == 201, turn.text
    turn_body = turn.json()
    assert turn_body["question"]
    assert turn_body["grounding"] is not None

    # Second call is idempotent while an unanswered turn exists.
    same = await client.post(f"/api/v1/sessions/{session_id}/turns", headers=_hdr(token))
    assert same.status_code == 201
    assert same.json()["id"] == turn_body["id"]

    answer = await client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_body['ordinal']}/answer",
        headers=_hdr(token),
        json={
            "answer": (
                "AWS is a public cloud. Kubernetes orchestrates containers across nodes. "
                "At my last job we used Terraform to codify the AWS VPC and reduced deploy time by 70 percent."
            ),
            "seconds_taken": 40,
        },
    )
    assert answer.status_code == 200, answer.text
    ev = answer.json()["evaluation"]
    assert 0.0 <= ev["overall"] <= 1.0
    assert answer.json()["adaptive_action"]["action"] in {
        "increase_difficulty", "follow_up", "probe_concept", "coach_intervention", "finish",
    }

    readiness = await client.get(
        f"/api/v1/projects/{project_id}/readiness/", headers=_hdr(token)
    )
    assert readiness.status_code == 200
    snap = readiness.json()
    assert snap["source"] == "turn"
    assert snap["session_id"] == session_id

    # Cannot re-answer the same turn.
    dup = await client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_body['ordinal']}/answer",
        headers=_hdr(token),
        json={"answer": "again"},
    )
    assert dup.status_code == 409

    # Ask another question so we have >=2 turns for the final report.
    turn2 = await client.post(f"/api/v1/sessions/{session_id}/turns", headers=_hdr(token))
    assert turn2.status_code == 201
    await client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn2.json()['ordinal']}/answer",
        headers=_hdr(token),
        json={"answer": "I don't know."},
    )

    finish = await client.post(f"/api/v1/sessions/{session_id}/finish", headers=_hdr(token))
    assert finish.status_code == 200
    body = finish.json()
    assert body["status"] == "completed"
    assert body["summary"]["turns_answered"] == 2


@pytest.mark.asyncio
async def test_starting_session_without_competency_map_rejected(client: AsyncClient) -> None:
    token = await _register_login(client, f"s-{uuid.uuid4().hex[:8]}@example.com")
    resp = await client.post(
        "/api/v1/projects/",
        headers=_hdr(token),
        json={"name": "Empty", "goal_type": "job_interview"},
    )
    project_id = resp.json()["id"]
    start = await client.post(
        f"/api/v1/projects/{project_id}/sessions/",
        headers=_hdr(token),
        json={"mode": "mock_interview"},
    )
    assert start.status_code == 409


@pytest.mark.asyncio
async def test_session_isolated_across_users(client: AsyncClient) -> None:
    token_a = await _register_login(client, f"s-{uuid.uuid4().hex[:8]}@example.com")
    token_b = await _register_login(client, f"s-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _prepare_project(client, token_a)
    start = await client.post(
        f"/api/v1/projects/{project_id}/sessions/",
        headers=_hdr(token_a),
        json={"mode": "mock_interview"},
    )
    session_id = start.json()["id"]

    resp = await client.get(f"/api/v1/sessions/{session_id}", headers=_hdr(token_b))
    assert resp.status_code == 404
    resp = await client.post(f"/api/v1/sessions/{session_id}/turns", headers=_hdr(token_b))
    assert resp.status_code == 404
