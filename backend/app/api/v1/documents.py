from __future__ import annotations

import mimetypes
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.auth import get_current_user
from app.config import settings
from app.db import get_session
from app.ingest import process_document
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.project import PreparationProject
from app.models.user import User
from app.schemas.chunk import ChunkResponse
from app.schemas.document import DocumentDownloadResponse, DocumentResponse

router = APIRouter()
project_router = APIRouter()


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


async def _load_owned_document(
    document_id: uuid.UUID, user: User, session: AsyncSession
) -> Document:
    stmt = (
        select(Document)
        .join(PreparationProject, PreparationProject.id == Document.project_id)
        .where(Document.id == document_id, PreparationProject.user_id == user.id)
    )
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@project_router.post(
    "/",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> Document:
    await _load_owned_project(project_id, current, session)

    body = await file.read()
    size = len(body)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if size > settings.document_max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.document_max_size_bytes} bytes",
        )

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime not in settings.document_allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {mime or 'unknown'}",
        )

    extension = ""
    if file.filename and "." in file.filename:
        extension = "." + file.filename.rsplit(".", 1)[-1].lower()
    storage_key = f"projects/{project_id}/{uuid.uuid4()}{extension}"

    await storage.put_object(storage_key, body, mime)

    document = Document(
        project_id=project_id,
        filename=file.filename or "upload",
        mime_type=mime,
        size_bytes=size,
        storage_key=storage_key,
        status="uploaded",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    background.add_task(process_document, document.id)
    return document


@project_router.get("/", response_model=list[DocumentResponse])
async def list_project_documents(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Document]:
    await _load_owned_project(project_id, current, session)
    result = await session.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Document:
    return await _load_owned_document(document_id, current, session)


@router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
async def download_document(
    document_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentDownloadResponse:
    document = await _load_owned_document(document_id, current, session)
    url = await storage.presigned_get_url(document.storage_key)
    return DocumentDownloadResponse(
        url=url, expires_in_seconds=settings.document_presign_ttl_seconds
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def list_document_chunks(
    document_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentChunk]:
    await _load_owned_document(document_id, current, session)
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordinal)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    document = await _load_owned_document(document_id, current, session)
    await storage.delete_object(document.storage_key)
    await session.delete(document)
    await session.commit()
