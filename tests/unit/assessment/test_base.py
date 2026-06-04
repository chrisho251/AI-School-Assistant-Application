"""Unit tests for generator base helpers — numbered_context + resolve_refs."""

from __future__ import annotations

import uuid

from asag.assessment.generators.base import numbered_context, resolve_refs
from asag.rag.retriever import ChunkResult


def _chunk(content: str) -> ChunkResult:
    return ChunkResult(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        content=content,
        content_type="text",
        page_number=None,
    )


def test_numbered_context_numbers_from_one() -> None:
    chunks = [_chunk("alpha"), _chunk("beta")]
    text, ref_map = numbered_context(chunks)
    assert "[1] alpha" in text
    assert "[2] beta" in text
    assert ref_map[1] is chunks[0]
    assert ref_map[2] is chunks[1]


def test_resolve_refs_maps_and_drops_out_of_range() -> None:
    chunks = [_chunk("a"), _chunk("b")]
    _, ref_map = numbered_context(chunks)
    # 1 -> chunk a, 99 -> dropped (out of range)
    ids = resolve_refs([1, 99], ref_map)
    assert ids == [chunks[0].id]


def test_resolve_refs_dedupes_preserving_order() -> None:
    chunks = [_chunk("a"), _chunk("b")]
    _, ref_map = numbered_context(chunks)
    ids = resolve_refs([2, 1, 2], ref_map)
    assert ids == [chunks[1].id, chunks[0].id]
