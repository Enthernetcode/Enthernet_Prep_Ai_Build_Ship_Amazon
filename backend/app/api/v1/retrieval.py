from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.db import get_session
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.project import PreparationProject
from app.models.user import User
from app.providers import EmbeddingRequest, get_embedding_provider
from app.schemas.retrieval import RetrievalMatch, RetrievalRequest, RetrievalResponse

router = APIRouter()


@router.post("/", response_model=RetrievalResponse)
async def retrieve(
    project_id: uuid.UUID,
    payload: RetrievalRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetrievalResponse:
    project = (
        await session.execute(
            select(PreparationProject).where(
                PreparationProject.id == project_id,
                PreparationProject.user_id == current.id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    k = payload.k or settings.retrieval_default_k

    provider = get_embedding_provider()
    embedded = await provider.embed(
        EmbeddingRequest(model=settings.embedding_model, texts=[payload.query])
    )
    query_vector = embedded.vectors[0]

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.ordinal,
            DocumentChunk.text,
            DocumentChunk.char_start,
            DocumentChunk.char_end,
            Document.filename,
            distance.label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.project_id == project_id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(k)
    )
    result = await session.execute(stmt)

    matches: list[RetrievalMatch] = []
    for row in result.all():
        matches.append(
            RetrievalMatch(
                chunk_id=row.id,
                document_id=row.document_id,
                document_filename=row.filename,
                ordinal=row.ordinal,
                text=row.text,
                score=1.0 - float(row.distance),
                char_start=row.char_start,
                char_end=row.char_end,
            )
        )
    return RetrievalResponse(query=payload.query, k=k, matches=matches)
