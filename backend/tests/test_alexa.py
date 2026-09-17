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


async def _make_project(client: AsyncClient, token: str, name: str = "Alexa P") -> str:
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


def _envelope(kind: str, intent: str | None = None, slots: dict | None = None, attrs: dict | None = None) -> dict:
    request: dict = {"type": kind}
    if kind == "IntentRequest" and intent:
        request["intent"] = {"name": intent, "slots": slots or {}}
    return {
        "version": "1.0",
        "session": {"attributes": attrs or {}},
        "context": {},
        "request": request,
    }


@pytest.mark.asyncio
async def test_alexa_requires_bearer_token(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/alexa", json=_envelope("LaunchRequest"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_alexa_launch_lists_projects(client: AsyncClient) -> None:
    token = await _register_login(client, f"al-{uuid.uuid4().hex[:8]}@example.com")
    await _make_project(client, token, name="Cloud Engineer")

    resp = await client.post(
        "/api/v1/alexa",
        headers=_hdr(token),
        json=_envelope("LaunchRequest"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Cloud Engineer" in body["response"]["outputSpeech"]["text"]


@pytest.mark.asyncio
async def test_alexa_start_interview_asks_question(client: AsyncClient) -> None:
    token = await _register_login(client, f"al-{uuid.uuid4().hex[:8]}@example.com")
    project_id = await _make_project(client, token)
    await _upload_and_wait(
        client, token, project_id,
        "Cloud Engineer with AWS Kubernetes Terraform experience. Reduced deploy time 70%.",
        "cv.txt",
    )
    ext = await client.post(
        f"/api/v1/projects/{project_id}/competencies/extract", headers=_hdr(token)
    )
    assert ext.status_code == 200

    resp = await client.post(
        "/api/v1/alexa",
        headers=_hdr(token),
        json=_envelope("IntentRequest", "StartInterviewIntent"),
    )
    assert resp.status_code == 200
    body = resp.json()
    speech = body["response"]["outputSpeech"]["text"]
    assert speech  # a real question
    assert "session_id" in body["sessionAttributes"]

    # Follow up with an answer, reusing the sessionAttributes.
    attrs = body["sessionAttributes"]
    answer = await client.post(
        "/api/v1/alexa",
        headers=_hdr(token),
        json=_envelope(
            "IntentRequest",
            "AnswerIntent",
            slots={"answer": {"value": "AWS is a cloud provider used to host Kubernetes clusters."}},
            attrs=attrs,
        ),
    )
    assert answer.status_code == 200
    assert answer.json()["response"]["outputSpeech"]["text"]


@pytest.mark.asyncio
async def test_alexa_help_and_stop(client: AsyncClient) -> None:
    token = await _register_login(client, f"al-{uuid.uuid4().hex[:8]}@example.com")
    help_resp = await client.post(
        "/api/v1/alexa",
        headers=_hdr(token),
        json=_envelope("IntentRequest", "AMAZON.HelpIntent"),
    )
    assert help_resp.status_code == 200
    assert help_resp.json()["response"]["shouldEndSession"] is False

    stop_resp = await client.post(
        "/api/v1/alexa",
        headers=_hdr(token),
        json=_envelope("IntentRequest", "AMAZON.StopIntent"),
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["response"]["shouldEndSession"] is True
