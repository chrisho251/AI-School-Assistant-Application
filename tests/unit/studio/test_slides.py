"""Unit tests for Marp rendering helpers — template output + format guard.

Pure functions only (no DB, no LLM, no Marp subprocess).

Run:
    uv run pytest tests/unit/studio/test_slides.py -v
"""

from __future__ import annotations

import uuid

import pytest

from asag.models.studio import Outline, Slide
from asag.studio.slides import marp_render, outline_to_marp


def _outline() -> Outline:
    return Outline(
        notebook_id=uuid.uuid4(),
        title="Photosynthesis 101",
        slides=[
            Slide(title="Photosynthesis 101", bullets=[]),
            Slide(
                title="Light Reactions",
                bullets=["Occur in thylakoid membranes", "Produce ATP and NADPH"],
                visual_hint="Thylakoid diagram",
                source_chunk_ids=[uuid.uuid4()],
            ),
            Slide(
                title="Calvin Cycle",
                bullets=["Fixes CO2 into glucose"],
                source_chunk_ids=[uuid.uuid4()],
            ),
        ],
    )


def test_outline_to_marp_structure() -> None:
    md = outline_to_marp(_outline())

    # Marp front-matter present.
    assert md.startswith("---\nmarp: true")
    # Title slide rendered as H1, content slides as H2.
    assert "# Photosynthesis 101" in md
    assert "## Light Reactions" in md
    assert "## Calvin Cycle" in md
    # Bullets rendered.
    assert "- Occur in thylakoid membranes" in md
    assert "- Fixes CO2 into glucose" in md
    # Visual hint rendered only where present.
    assert "Thylakoid diagram" in md
    # Slide separators: front-matter close + one per content slide (2).
    assert md.count("\n---\n") >= 2


def test_outline_to_marp_title_not_duplicated_as_content() -> None:
    md = outline_to_marp(_outline())
    # The first slide is the title slide (H1); it must not also appear as an H2.
    assert "## Photosynthesis 101" not in md


def test_outline_to_marp_keeps_content_when_no_title_slide() -> None:
    """If the model omits a bullet-less title slide, no content slide is dropped."""
    outline = Outline(
        notebook_id=uuid.uuid4(),
        title="Deck Title",
        slides=[
            # First slide already has bullets (no dedicated title slide).
            Slide(title="First Content", bullets=["fact one"], source_chunk_ids=[uuid.uuid4()]),
            Slide(title="Second Content", bullets=["fact two"], source_chunk_ids=[uuid.uuid4()]),
        ],
    )
    md = outline_to_marp(outline)
    assert "# Deck Title" in md  # title still rendered from outline.title
    assert "## First Content" in md  # would be dropped by a positional slides[1:]
    assert "## Second Content" in md
    assert "- fact one" in md


async def test_marp_render_rejects_unknown_format(tmp_path) -> None:  # type: ignore[no-untyped-def]
    md = tmp_path / "deck.md"
    md.write_text("# x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported Marp format"):
        await marp_render(md, tmp_path / "out.pdf", "pdf")
