from __future__ import annotations

import asyncio
import logging
import uuid

from botocore.exceptions import ClientError

from sqlalchemy import select

from app.agents.base import AgentContext
from app.agents.document import DocumentAgent
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.providers import EmbeddingRequest, get_embedding_provider
from app.storage import _client as _s3_client

logger = logging.getLogger(__name__)


async def _fetch_body(storage_key: str) -> bytes:
    def _sync() -> bytes:
        obj = _s3_client().get_object(Bucket=settings.s3_bucket, Key=storage_key)
        return obj["Body"].read()

    return await asyncio.to_thread(_sync)


async def _embed_document_chunks(session, document: Document) -> None:
    """Batch-embed all chunks for `document` and persist the vectors."""
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.ordinal)
    )
    chunks = list(result.scalars().all())
    if not chunks:
        return
    provider = get_embedding_provider()
    response = await provider.embed(
        EmbeddingRequest(model=settings.embedding_model, texts=[c.text for c in chunks])
    )
    for chunk, vector in zip(chunks, response.vectors, strict=True):
        chunk.embedding = vector
    await session.commit()


async def process_document(document_id: uuid.UUID) -> None:
    """Background job: extract text + write chunks + update Document.status.

    Opens its own AsyncSession — the request that scheduled this has long since
    closed its own session by the time we run.
    """
    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("process_document: %s not found", document_id)
            return
        document.status = "processing"
        document.error = None
        await session.commit()

        try:
            body = await _fetch_body(document.storage_key)
            agent = DocumentAgent()
            result = await agent.execute(
                AgentContext(
                    user_id="system",
                    project_id=str(document.project_id),
                    extra={"document_id": str(document.id)},
                ),
                tools={"mime_type": document.mime_type, "body": body},
            )
            if result.status != "success":
                document.status = "failed"
                document.error = str(result.result.get("reason", "extraction failed"))[:1000]
                await session.commit()
                return

            session.add_all(
                DocumentChunk(
                    document_id=document.id,
                    ordinal=chunk["ordinal"],
                    text=chunk["text"],
                    char_start=chunk["char_start"],
                    char_end=chunk["char_end"],
                )
                for chunk in result.result["chunks"]
            )
            await session.commit()

            await _embed_document_chunks(session, document)

            document.status = "processed"
            document.error = None
            await session.commit()
        except ClientError as exc:
            document.status = "failed"
            document.error = f"storage error: {exc.response.get('Error', {}).get('Code', 'unknown')}"[:1000]
            await session.commit()
        except Exception as exc:
            logger.exception("process_document %s failed", document_id)
            document.status = "failed"
            document.error = f"{type(exc).__name__}: {exc}"[:1000]
            await session.commit()
