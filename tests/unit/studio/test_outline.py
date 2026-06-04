"""Unit tests for the slide outline generator — grounding + ref resolution.

LLM and DB are mocked; verifies reference numbers resolve to real chunk UUIDs and
that out-of-range refs are dropped (anti-hallucination guarantee).

Run:
    uv run pytest tests/unit/studio/test_outline.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

import pytest

from asag.models.studio import Outline
from asag.rag.retriever import ChunkResult
from asag.studio.outline import _OutlineDraft, _SlideDraft, generate_outline


def _chunk(content: str) -> ChunkResult:
    return ChunkResult(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        content=content,
        content_type="text",
        page_number=None,
    )


def _draft() -> _OutlineDraft:
    return _OutlineDraft(
        deck_title="Cell Biology Basics",
        slides=[
            _SlideDraft(title="Cell Biology Basics", bullets=[], source_refs=[]),
            _SlideDraft(
                title="The Mitochondrion",
                bullets=["Powerhouse of the cell", "Produces ATP"],
                visual_hint="Diagram of a mitochondrion",
                source_refs=[1, 2],
            ),
            _SlideDraft(
                title="Ungrounded claim",
                bullets=["Cells contain magic"],
                source_refs=[99],  # out of range → dropped → ungrounded content slide
            ),
        ],
    )


@pytest.fixture
def _patched_repo() -> list[ChunkResult]:
    return [_chunk("Mitochondria are the powerhouse."), _chunk("ATP is the energy currency.")]


async def test_generate_outline_resolves_refs(_patched_repo: list[ChunkResult]) -> None:
    chunks = _patched_repo
    fake_repo = AsyncMock()
    fake_repo.fetch_notebook_chunks = AsyncMock(return_value=chunks)
    notebook_id = uuid.uuid4()

    with (
        patch("asag.studio.outline.StudioRepository", return_value=fake_repo),
        patch("asag.studio.outline.structured_output", new=AsyncMock(return_value=_draft())),
    ):
        outline = await generate_outline(notebook_id, pool=AsyncMock(), n_slides=3)

    assert isinstance(outline, Outline)
    assert outline.title == "Cell Biology Basics"
    assert len(outline.slides) == 3

    # Title slide: no sources.
    assert outline.slides[0].source_chunk_ids == []
    # Content slide: refs [1,2] → the two real chunk UUIDs, order preserved.
    assert outline.slides[1].source_chunk_ids == [chunks[0].id, chunks[1].id]
    # Out-of-range ref [99] dropped → ungrounded content slide.
    assert outline.slides[2].source_chunk_ids == []


async def test_generate_outline_raises_without_chunks() -> None:
    fake_repo = AsyncMock()
    fake_repo.fetch_notebook_chunks = AsyncMock(return_value=[])
    with (
        patch("asag.studio.outline.StudioRepository", return_value=fake_repo),
        pytest.raises(ValueError, match="no ingested chunks"),
    ):
        await generate_outline(uuid.uuid4(), pool=AsyncMock())
