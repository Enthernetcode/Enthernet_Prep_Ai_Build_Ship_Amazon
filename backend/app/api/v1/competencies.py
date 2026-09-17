from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext
from app.agents.knowledge import KnowledgeExtractionAgent
from app.auth import get_current_user
from app.db import get_session
from app.models.chunk import DocumentChunk
from app.models.competency import CompetencyItem
from app.models.document import Document
from app.models.project import PreparationProject
from app.models.user import User
from app.schemas.competency import CompetencyExtractResponse, CompetencyResponse

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


@router.get("/", response_model=list[CompetencyResponse])
async def list_competencies(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CompetencyItem]:
    await _load_owned_project(project_id, current, session)
    result = await session.execute(
        select(CompetencyItem)
        .where(CompetencyItem.project_id == project_id)
        .order_by(CompetencyItem.confidence.desc(), CompetencyItem.label.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/extract",
    response_model=CompetencyExtractResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_competencies(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompetencyExtractResponse:
    await _load_owned_project(project_id, current, session)

    chunks_stmt = (
        select(
            DocumentChunk.document_id,
            DocumentChunk.ordinal,
            DocumentChunk.text,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.asc(), DocumentChunk.ordinal.asc())
    )
    rows = (await session.execute(chunks_stmt)).all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No processed chunks — upload and wait for ingestion first.",
        )

    tools_chunks = [
        {"document_id": str(r.document_id), "ordinal": r.ordinal, "text": r.text}
        for r in rows
    ]
    agent = KnowledgeExtractionAgent()
    result = await agent.execute(
        AgentContext(user_id=str(current.id), project_id=str(project_id)),
        tools={"chunks": tools_chunks},
    )
    if result.status != "success":
        raise HTTPException(status_code=500, detail="knowledge extraction failed")

    # Upsert by (kind, lower(label)); keep highest-confidence source.
    existing_rows = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project_id)
        )
    ).scalars().all()
    existing_map = {(c.kind, c.label.lower()): c for c in existing_rows}

    kept = 0
    for item in result.result["items"]:
        key = (item["kind"], item["label"].lower())
        source_doc = item.get("source_document_id")
        source_doc_uuid = uuid.UUID(source_doc) if source_doc else None
        if key in existing_map:
            row = existing_map[key]
            if item["confidence"] > row.confidence:
                row.confidence = item["confidence"]
                row.source_document_id = source_doc_uuid or row.source_document_id
                row.source_chunk_ordinal = (
                    item.get("source_chunk_ordinal") or row.source_chunk_ordinal
                )
        else:
            session.add(
                CompetencyItem(
                    project_id=project_id,
                    kind=item["kind"],
                    label=item["label"][:300],
                    confidence=item["confidence"],
                    source_document_id=source_doc_uuid,
                    source_chunk_ordinal=item.get("source_chunk_ordinal"),
                )
            )
            kept += 1

    await session.commit()

    total = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project_id)
        )
    ).scalars().all()

    return CompetencyExtractResponse(
        project_id=project_id,
        extracted=result.result["raw_count"],
        kept=kept,
        total=len(total),
        kinds=result.result["kinds"],
    )
