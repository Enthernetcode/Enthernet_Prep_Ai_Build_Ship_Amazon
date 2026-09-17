from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult
from app.chunker import chunk_text
from app.config import settings
from app.extract import UnsupportedMimeError, extract_text


class DocumentAgent(Agent):
    """§9 Document Agent — text extraction + chunk preparation for the MVP formats.

    Classification, section detection and richer metadata land in follow-up PRs.
    """

    name = "document"
    description = "Extract text from an uploaded document and produce chunks."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        mime: str = tools["mime_type"]
        body: bytes = tools["body"]

        try:
            text = extract_text(mime, body)
        except UnsupportedMimeError as exc:
            return AgentResult(
                agent=self.name,
                status="error",
                result={"reason": str(exc)},
            )

        chunks = chunk_text(
            text,
            size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )
        return AgentResult(
            agent=self.name,
            status="success",
            confidence=1.0 if text else 0.0,
            result={
                "text_length": len(text),
                "chunk_count": len(chunks),
                "chunks": [
                    {
                        "ordinal": c.ordinal,
                        "text": c.text,
                        "char_start": c.char_start,
                        "char_end": c.char_end,
                    }
                    for c in chunks
                ],
            },
            warnings=[] if text else ["Extraction produced empty text"],
        )
