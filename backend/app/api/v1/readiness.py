from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import readiness as readiness_engine
from app.auth import get_current_user
from app.db import get_session
from app.models.competency import CompetencyItem
from app.models.project import PreparationProject
from app.models.readiness import ReadinessSnapshot
from app.models.user import User
from app.schemas.readiness import ReadinessSnapshotResponse

router = APIRouter()


async def _load_owned_project(
    project_id: uuid.UUID, user: User, session: AsyncSession
) -> PreparationProject:
    result = await session.execute(
        select(PreparationProject).where(
            PreparationProject.id == project_id,
            PreparationProject.user_id == user.id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _persist_snapshot(
    session: AsyncSession,
    project_id: uuid.UUID,
    session_id: uuid.UUID | None,
    source: str,
    scores: dict,
) -> ReadinessSnapshot:
    snapshot = ReadinessSnapshot(
        project_id=project_id,
        session_id=session_id,
        source=source,
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
    await session.refresh(snapshot)
    return snapshot


@router.get("/", response_model=ReadinessSnapshotResponse)
async def get_readiness(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReadinessSnapshot:
    await _load_owned_project(project_id, current, session)
    result = await session.execute(
        select(ReadinessSnapshot)
        .where(ReadinessSnapshot.project_id == project_id)
        .order_by(ReadinessSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No readiness snapshot yet — call /readiness/baseline first.",
        )
    return snapshot


@router.post(
    "/baseline",
    response_model=ReadinessSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def compute_baseline(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReadinessSnapshot:
    await _load_owned_project(project_id, current, session)
    competencies = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project_id)
        )
    ).scalars().all()
    kinds: dict[str, int] = {}
    for c in competencies:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    scores = readiness_engine.baseline_from_coverage(len(competencies), kinds)
    return await _persist_snapshot(
        session, project_id, None, "baseline", scores
    )
