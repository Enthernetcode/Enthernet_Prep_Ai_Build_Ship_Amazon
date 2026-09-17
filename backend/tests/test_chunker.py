from __future__ import annotations

import pytest

from app.chunker import chunk_text


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("", size=100, overlap=10) == []


def test_single_short_paragraph_is_one_chunk() -> None:
    text = "This fits comfortably."
    chunks = chunk_text(text, size=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].ordinal == 0


def test_paragraphs_get_grouped_greedily() -> None:
    para = "abcdefghij"  # 10 chars
    text = "\n\n".join([para] * 5)  # ~54 chars total
    chunks = chunk_text(text, size=30, overlap=0)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.ordinal == i
        assert c.char_end > c.char_start


def test_paragraph_larger_than_size_gets_hard_split() -> None:
    long_para = "x" * 250
    chunks = chunk_text(long_para, size=100, overlap=20)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 100 + 20 for c in chunks)  # size + overlap ceiling
    concatenated = "".join(c.text for c in chunks)
    assert "x" in concatenated
    assert len(concatenated) >= 250


def test_overlap_repeats_tail() -> None:
    text = "aaaa\n\nbbbb\n\ncccc\n\ndddd\n\neeee"
    chunks = chunk_text(text, size=12, overlap=4)
    assert len(chunks) >= 2
    for prev, curr in zip(chunks, chunks[1:]):
        assert curr.text[: min(4, len(curr.text))] in prev.text or prev.text[-4:] in curr.text


def test_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("hello", size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("hello", size=10, overlap=-1)
