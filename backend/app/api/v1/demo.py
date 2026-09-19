"""Demo seed endpoint — creates a ready-to-record demo user + project in one call.

Guarded by `settings.app_env`; non-dev environments return 404 so this can
never be reached in production even if the route is mounted by accident.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.agents.base import AgentContext
from app.agents.knowledge import KnowledgeExtractionAgent
from app.auth import create_access_token, hash_password
from app.config import settings
from app.db import AsyncSessionLocal, get_session
from app.ingest import process_document
from app.models.chunk import DocumentChunk
from app.models.competency import CompetencyItem
from app.models.document import Document
from app.models.project import PreparationProject
from app.models.readiness import ReadinessSnapshot
from app.models.user import User
from app.readiness import baseline_from_coverage

router = APIRouter()

_ALLOWED_ENVS = {"development", "demo", "test"}
_DEMO_PROJECT_NAME = "Cloud Engineer @ Enthernet"
_ASSET_DIR = Path(__file__).parent / "demo_assets"


class DemoSeedRequest(BaseModel):
    email: EmailStr = "demo@enthernet.dev"
    password: str = Field(default="demo-password-2026", min_length=8, max_length=128)


class DemoSeedResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    project_id: uuid.UUID
    dashboard_path: str
    competencies: int
    baseline_readiness: float


async def _get_or_create_user(session: AsyncSession, email: str, password: str) -> User:
    row = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if row:
        return row
    user = User(email=email.lower(), password_hash=hash_password(password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return (
            await session.execute(select(User).where(User.email == email.lower()))
        ).scalar_one()
    await session.refresh(user)
    return user


async def _get_or_create_project(session: AsyncSession, user: User) -> PreparationProject:
    row = (
        await session.execute(
            select(PreparationProject).where(
                PreparationProject.user_id == user.id,
                PreparationProject.name == _DEMO_PROJECT_NAME,
            )
        )
    ).scalar_one_or_none()
    if row:
        return row
    project = PreparationProject(
        user_id=user.id,
        name=_DEMO_PROJECT_NAME,
        goal_type="job_interview",
        goal_description="Prep for the Enthernet Senior Cloud Engineer loop.",
        difficulty=4,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def _seed_document(
    session: AsyncSession,
    project: PreparationProject,
    filename: str,
    body: bytes,
) -> Document:
    existing = (
        await session.execute(
            select(Document).where(
                Document.project_id == project.id, Document.filename == filename
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    storage_key = f"projects/{project.id}/{uuid.uuid4()}.txt"
    await storage.put_object(storage_key, body, "text/plain")
    document = Document(
        project_id=project.id,
        filename=filename,
        mime_type="text/plain",
        size_bytes=len(body),
        storage_key=storage_key,
        status="uploaded",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def _wait_for_processed(
    document_id: uuid.UUID, timeout: float = 20.0
) -> Document:
    """Poll on a fresh AsyncSession per attempt — the request-scoped session
    is inside an implicit transaction and won't see updates the background
    ingest task has committed."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        async with AsyncSessionLocal() as fresh:
            doc = await fresh.get(Document, document_id)
            if doc is None:
                raise HTTPException(status_code=500, detail="seed document vanished")
            if doc.status == "processed":
                return doc
            if doc.status == "failed":
                raise HTTPException(
                    status_code=500,
                    detail=f"seed document failed: {doc.error}",
                )
        if asyncio.get_event_loop().time() > deadline:
            raise HTTPException(
                status_code=504,
                detail=f"seed document still {doc.status} after {timeout}s",
            )
        await asyncio.sleep(0.2)


async def _extract_competencies(
    session: AsyncSession, project: PreparationProject
) -> tuple[int, dict[str, int]]:
    chunks = (
        await session.execute(
            select(
                DocumentChunk.document_id,
                DocumentChunk.ordinal,
                DocumentChunk.text,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.project_id == project.id)
            .order_by(Document.created_at.asc(), DocumentChunk.ordinal.asc())
        )
    ).all()
    if not chunks:
        return 0, {}
    agent = KnowledgeExtractionAgent()
    result = await agent.execute(
        AgentContext(user_id=str(project.user_id), project_id=str(project.id)),
        tools={
            "chunks": [
                {"document_id": str(r.document_id), "ordinal": r.ordinal, "text": r.text}
                for r in chunks
            ]
        },
    )
    existing = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project.id)
        )
    ).scalars().all()
    existing_map = {(c.kind, c.label.lower()): c for c in existing}
    for item in result.result["items"]:
        key = (item["kind"], item["label"].lower())
        if key in existing_map:
            continue
        session.add(
            CompetencyItem(
                project_id=project.id,
                kind=item["kind"],
                label=item["label"][:300],
                confidence=item["confidence"],
                source_document_id=(
                    uuid.UUID(item["source_document_id"])
                    if item.get("source_document_id")
                    else None
                ),
                source_chunk_ordinal=item.get("source_chunk_ordinal"),
            )
        )
    await session.commit()
    total = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project.id)
        )
    ).scalars().all()
    return len(total), result.result["kinds"]


async def _seed_baseline_readiness(
    session: AsyncSession, project: PreparationProject, kinds: dict[str, int], total: int
) -> float:
    scores = baseline_from_coverage(total, kinds)
    snapshot = ReadinessSnapshot(
        project_id=project.id,
        session_id=None,
        source="baseline",
        overall=scores["overall"],
        knowledge=scores["knowledge"],
        communication=scores["communication"],
        evidence=scores["evidence"],
        conciseness=scores["conciseness"],
        pressure=scores["pressure"],
        consistency=scores["consistency"],
        coverage=scores["coverage"],
        detail=scores.get("detail"),
    )
    session.add(snapshot)
    await session.commit()
    return scores["overall"]


@router.post("/seed", response_model=DemoSeedResponse)
async def seed_demo(
    payload: DemoSeedRequest | None = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> DemoSeedResponse:
    if settings.app_env.lower() not in _ALLOWED_ENVS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    body = payload or DemoSeedRequest()

    user = await _get_or_create_user(session, body.email, body.password)
    project = await _get_or_create_project(session, user)

    cv = (_ASSET_DIR / "cv.txt").read_bytes()
    jd = (_ASSET_DIR / "jd.txt").read_bytes()

    cv_doc = await _seed_document(session, project, "ruth-cv.txt", cv)
    jd_doc = await _seed_document(session, project, "enthernet-jd.txt", jd)

    # Kick ingest jobs off the request thread — they open their own sessions.
    for doc in (cv_doc, jd_doc):
        if doc.status != "processed":
            asyncio.create_task(process_document(doc.id))

    await _wait_for_processed(cv_doc.id)
    await _wait_for_processed(jd_doc.id)

    total, kinds = await _extract_competencies(session, project)
    baseline = await _seed_baseline_readiness(session, project, kinds, total)

    return DemoSeedResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        project_id=project.id,
        dashboard_path=f"/projects/{project.id}",
        competencies=total,
        baseline_readiness=baseline,
    )
