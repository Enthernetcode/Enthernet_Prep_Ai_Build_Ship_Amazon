from __future__ import annotations

import io
import re

from docx import Document as _DocxDocument
from pypdf import PdfReader

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


class UnsupportedMimeError(ValueError):
    pass


def _normalize(text: str) -> str:
    text = _WHITESPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def _extract_pdf(body: bytes) -> str:
    reader = PdfReader(io.BytesIO(body))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _extract_docx(body: bytes) -> str:
    doc = _DocxDocument(io.BytesIO(body))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def extract_text(mime: str, body: bytes) -> str:
    if mime == "application/pdf":
        raw = _extract_pdf(body)
    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        raw = _extract_docx(body)
    elif mime in {"text/plain", "text/markdown"}:
        raw = _extract_text(body)
    else:
        raise UnsupportedMimeError(f"No extractor for mime={mime!r}")
    return _normalize(raw)
