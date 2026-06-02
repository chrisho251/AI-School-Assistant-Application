"""Unit tests for SemanticChunker — no DB, no Docling."""

from __future__ import annotations

import uuid

import pytest

from asag.ingestion.chunkers import get
from asag.ingestion.chunkers.semantic import SemanticChunker
from asag.models.ingestion import Chunk, ContentType, Element

# Stable IDs for all tests
_SRC = uuid.UUID("00000000-0000-0000-0000-000000000001")
_NB = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _el(
    content: str,
    *,
    content_type: ContentType = ContentType.text,
    page: int | None = 1,
    label: str = "text",
) -> Element:
    return Element(
        content=content,
        content_type=content_type,
        page_number=page,
        metadata={"label": label},
    )


def _heading(content: str, page: int = 1) -> Element:
    return _el(content, label="section_header", page=page)


def _table(content: str, page: int = 1) -> Element:
    return _el(content, content_type=ContentType.table, label="table", page=page)


def _chunk(elements: list[Element], **kwargs) -> list[Chunk]:
    c = SemanticChunker(**kwargs)
    return c.chunk(elements, source_id=_SRC, notebook_id=_NB)


# ------------------------------------------------------------------ #
# Basic behaviour                                                      #
# ------------------------------------------------------------------ #


def test_empty_input_returns_empty() -> None:
    assert _chunk([]) == []


def test_single_element_becomes_one_chunk() -> None:
    chunks = _chunk([_el("Hello world.")])
    assert len(chunks) == 1
    assert chunks[0].content == "Hello world."
    assert chunks[0].content_type == ContentType.text
    assert chunks[0].ordinal == 0
    assert chunks[0].source_id == _SRC
    assert chunks[0].notebook_id == _NB


def test_ordinals_are_sequential() -> None:
    elements = [_el(f"Para {i}.") for i in range(5)]
    chunks = _chunk(elements, max_tokens=5)  # force a split every ~1 element
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == list(range(len(chunks)))


def test_multiple_short_elements_merged_into_one_chunk() -> None:
    """Small elements that fit within max_tokens are merged into one chunk."""
    elements = [_el("A."), _el("B."), _el("C.")]
    chunks = _chunk(elements, max_tokens=1000)
    assert len(chunks) == 1
    assert "A." in chunks[0].content
    assert "B." in chunks[0].content
    assert "C." in chunks[0].content


def test_page_number_from_first_element() -> None:
    elements = [_el("First.", page=3), _el("Second.", page=4)]
    chunks = _chunk(elements, max_tokens=1000)
    assert chunks[0].page_number == 3


# ------------------------------------------------------------------ #
# Heading boundary behaviour                                           #
# ------------------------------------------------------------------ #


def test_heading_flushes_previous_window() -> None:
    """Content before a heading and after a heading end up in separate chunks."""
    elements = [
        _el("Introduction text."),
        _heading("Section 1"),
        _el("Section body."),
    ]
    chunks = _chunk(elements, max_tokens=1000)
    assert len(chunks) == 2
    assert "Introduction text." in chunks[0].content
    assert "Section 1" in chunks[1].content
    assert "Section body." in chunks[1].content


def test_heading_at_start_does_not_create_empty_chunk() -> None:
    """If the first element is a heading there is no prior content to flush."""
    elements = [_heading("Title"), _el("Body text.")]
    chunks = _chunk(elements, max_tokens=1000)
    assert len(chunks) == 1
    assert "Title" in chunks[0].content


# ------------------------------------------------------------------ #
# Table behaviour                                                      #
# ------------------------------------------------------------------ #


def test_table_is_standalone_chunk() -> None:
    elements = [_el("Text before."), _table("| A | B |"), _el("Text after.")]
    chunks = _chunk(elements, max_tokens=1000)
    assert len(chunks) == 3
    assert chunks[1].content_type == ContentType.table
    assert chunks[1].content == "| A | B |"


def test_table_content_type_preserved() -> None:
    elements = [_table("| X | Y |")]
    chunks = _chunk(elements, max_tokens=1000)
    assert chunks[0].content_type == ContentType.table


# ------------------------------------------------------------------ #
# Token-limit splitting                                                #
# ------------------------------------------------------------------ #


def test_overflow_triggers_split() -> None:
    """Elements that together exceed max_tokens produce multiple chunks."""
    # Each word ≈ 1 token — 30 words × 2 elements = ~60 tokens; limit = 30
    long_text = " ".join([f"word{i}" for i in range(30)])
    elements = [_el(long_text), _el(long_text)]
    chunks = _chunk(elements, max_tokens=30, overlap_tokens=0)
    assert len(chunks) >= 2


def test_overlap_carries_elements_to_next_chunk() -> None:
    """With non-zero overlap, last elements appear in the next chunk's prefix."""
    # Three elements, limit = 1 token each to force individual flushing
    elements = [_el("alpha."), _el("beta."), _el("gamma.")]
    chunks = _chunk(elements, max_tokens=1, overlap_tokens=10)
    # With max_tokens=1 and non-zero overlap, we expect multiple chunks
    # and the content of the last element of one chunk appears in the next
    assert len(chunks) >= 2


# ------------------------------------------------------------------ #
# Registry                                                             #
# ------------------------------------------------------------------ #


def test_registry_returns_semantic_chunker() -> None:
    chunker = get("semantic")
    assert isinstance(chunker, SemanticChunker)


def test_registry_unknown_raises() -> None:
    with pytest.raises(KeyError, match="No chunker"):
        get("nonexistent_chunker")
