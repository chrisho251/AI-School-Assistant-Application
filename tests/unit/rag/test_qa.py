"""Unit tests for pure functions in rag/qa.py."""

from __future__ import annotations

import uuid

from asag.rag.qa import _build_context, _extract_citations
from asag.rag.retriever import ChunkResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(
    *,
    chunk_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    content: str = "test content",
    page_number: int | None = None,
) -> ChunkResult:
    return ChunkResult(
        id=chunk_id or uuid.uuid4(),
        source_id=source_id or uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        content=content,
        content_type="text",
        page_number=page_number,
        score=0.9,
    )


# ---------------------------------------------------------------------------
# Tests — _build_context
# ---------------------------------------------------------------------------


def test_build_context_numbers_chunks_from_one() -> None:
    """Each chunk is labelled [1], [2], … in order."""
    chunks = [_chunk(content="first"), _chunk(content="second")]
    context, ref_map = _build_context(chunks)

    assert "[1]" in context
    assert "[2]" in context
    assert "first" in context
    assert "second" in context
    assert ref_map[1] is chunks[0]
    assert ref_map[2] is chunks[1]


def test_build_context_empty_list() -> None:
    """Empty chunk list produces empty context and empty ref_map."""
    context, ref_map = _build_context([])

    assert context == ""
    assert ref_map == {}


def test_build_context_includes_page_when_present() -> None:
    """Chunks with page_number include 'page N' in the context block header."""
    c = _chunk(content="intro", page_number=7)
    context, _ = _build_context([c])

    assert "page 7" in context


def test_build_context_omits_page_when_none() -> None:
    """Chunks with page_number=None have no 'page' text in the header."""
    c = _chunk(content="intro", page_number=None)
    context, _ = _build_context([c])

    assert "page" not in context


def test_build_context_source_id_in_header() -> None:
    """The source_id appears in each context block header for auditability."""
    src = uuid.uuid4()
    c = _chunk(source_id=src, content="body text")
    context, _ = _build_context([c])

    assert str(src) in context


# ---------------------------------------------------------------------------
# Tests — _extract_citations
# ---------------------------------------------------------------------------


def test_extract_citations_parses_single_ref() -> None:
    """[1] in text maps to the first chunk in ref_map."""
    cid = uuid.uuid4()
    src = uuid.uuid4()
    c = _chunk(chunk_id=cid, source_id=src, page_number=3)
    _, ref_map = _build_context([c])

    citations = _extract_citations("Answer text [1] here.", ref_map)

    assert len(citations) == 1
    assert citations[0].chunk_id == cid
    assert citations[0].source_id == src
    assert citations[0].page_number == 3


def test_extract_citations_preserves_order_of_first_appearance() -> None:
    """Citations are ordered by first [N] occurrence, not by N value."""
    c1, c2 = _chunk(), _chunk()
    _, ref_map = _build_context([c1, c2])

    # [2] appears before [1] in the text
    citations = _extract_citations("See [2] and also [1].", ref_map)

    assert citations[0].chunk_id == c2.id
    assert citations[1].chunk_id == c1.id


def test_extract_citations_deduplicates() -> None:
    """Repeated [N] references produce only one Citation per chunk."""
    c = _chunk()
    _, ref_map = _build_context([c])

    citations = _extract_citations("Point A [1]. Point B [1]. Point C [1].", ref_map)

    assert len(citations) == 1


def test_extract_citations_ignores_out_of_range_refs() -> None:
    """[5] when only 2 chunks exist is silently skipped."""
    _, ref_map = _build_context([_chunk(), _chunk()])

    citations = _extract_citations("See [5] and [1].", ref_map)

    # Only [1] is valid
    assert len(citations) == 1


def test_extract_citations_empty_text() -> None:
    """Empty text returns empty citation list without errors."""
    _, ref_map = _build_context([_chunk()])

    assert _extract_citations("", ref_map) == []


def test_extract_citations_no_refs_in_text() -> None:
    """Text with no [N] pattern returns empty list."""
    _, ref_map = _build_context([_chunk()])

    assert _extract_citations("No citations here.", ref_map) == []


def test_extract_citations_refusal_phrase_produces_no_citations() -> None:
    """The refusal phrase contains no [N] refs and returns empty list."""
    from asag.rag.qa import REFUSAL_PHRASE

    _, ref_map = _build_context([_chunk()])

    assert _extract_citations(REFUSAL_PHRASE, ref_map) == []
