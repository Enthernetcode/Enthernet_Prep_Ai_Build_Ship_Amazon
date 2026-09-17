from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    char_start: int
    char_end: int


def _hard_split(text: str, start_offset: int, size: int) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for i in range(0, len(text), size):
        piece = text[i : i + size]
        out.append((piece, start_offset + i, start_offset + i + len(piece)))
    return out


def chunk_text(text: str, size: int, overlap: int) -> list[Chunk]:
    """Paragraph-greedy chunker with prefix overlap.

    - Split on blank lines into paragraphs; hard-split any paragraph longer
      than `size` into `size`-char pieces.
    - Greedily pack pieces into chunks of up to `size` characters.
    - After packing, prepend up to `overlap` chars of the previous chunk's
      tail to each subsequent chunk (so overlapped chunks may reach
      `size + overlap` chars — the overlap is context, not payload).
    """
    if size <= 0:
        raise ValueError("size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = text.strip()
    if not text:
        return []

    paragraphs: list[tuple[str, int]] = []
    cursor = 0
    for raw in text.split("\n\n"):
        stripped = raw.strip()
        if not stripped:
            cursor += len(raw) + 2
            continue
        start = text.find(raw, cursor)
        paragraphs.append((raw, start))
        cursor = start + len(raw)

    pieces: list[tuple[str, int, int]] = []
    for para, para_start in paragraphs:
        if len(para) > size:
            pieces.extend(_hard_split(para, para_start, size))
        else:
            pieces.append((para, para_start, para_start + len(para)))

    packed: list[tuple[str, int, int]] = []
    buf_text = ""
    buf_start: int | None = None
    buf_end = 0

    for piece_text, piece_start, piece_end in pieces:
        sep = "\n\n" if buf_text else ""
        candidate_len = len(buf_text) + len(sep) + len(piece_text)
        if buf_text and candidate_len > size:
            packed.append((buf_text, buf_start or 0, buf_end))
            buf_text = piece_text
            buf_start = piece_start
        elif not buf_text:
            buf_text = piece_text
            buf_start = piece_start
        else:
            buf_text = buf_text + sep + piece_text
        buf_end = piece_end
    if buf_text:
        packed.append((buf_text, buf_start or 0, buf_end))

    chunks: list[Chunk] = []
    for i, (chunk_text_, chunk_start, chunk_end) in enumerate(packed):
        if i == 0 or overlap == 0:
            chunks.append(Chunk(ordinal=i, text=chunk_text_, char_start=chunk_start, char_end=chunk_end))
            continue
        prev_text, prev_start, prev_end = packed[i - 1]
        prefix = prev_text[-overlap:]
        chunks.append(
            Chunk(
                ordinal=i,
                text=prefix + chunk_text_,
                char_start=prev_end - len(prefix),
                char_end=chunk_end,
            )
        )
    return chunks
