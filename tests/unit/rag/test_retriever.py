"""Unit tests for retriever pure functions (no DB or TEI required)."""

from __future__ import annotations

import uuid

import pytest

from asag.rag.retriever import ChunkResult, reciprocal_rank_fusion


def _chunk(content: str = "text", score: float = 0.0) -> ChunkResult:
    return ChunkResult(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        content=content,
        content_type="text",
        page_number=None,
        score=score,
    )


def test_rrf_single_list_preserves_order() -> None:
    """With one list, RRF order = input order."""
    chunks = [_chunk(f"doc{i}") for i in range(3)]
    result = reciprocal_rank_fusion(chunks)
    assert [c.content for c in result] == ["doc0", "doc1", "doc2"]


def test_rrf_overlapping_lists_boosts_common_docs() -> None:
    """A chunk appearing in both lists gets a higher fused score."""
    shared = _chunk("shared")
    unique_a = _chunk("only_a")
    unique_b = _chunk("only_b")

    list_a = [shared, unique_a]  # shared at rank 1 in list A
    list_b = [shared, unique_b]  # shared at rank 1 in list B

    result = reciprocal_rank_fusion(list_a, list_b)
    # shared accumulates 2× 1/(60+1) ≈ 0.0328 > unique_* score of 1/(60+2) ≈ 0.0161
    assert result[0].id == shared.id


def test_rrf_scores_are_written_to_chunk() -> None:
    """After RRF, chunk.score == the computed RRF score."""
    c = _chunk("doc")
    result = reciprocal_rank_fusion([c])
    expected_score = 1.0 / (60 + 1)
    assert result[0].score == pytest.approx(expected_score)


def test_rrf_empty_lists() -> None:
    """No input lists → empty result."""
    assert reciprocal_rank_fusion() == []


def test_rrf_two_lists_deduplication() -> None:
    """Same chunk in both lists appears only once in output."""
    shared = _chunk("shared")
    result = reciprocal_rank_fusion([shared], [shared])
    assert len(result) == 1
