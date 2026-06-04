"""Pydantic models for the studio domain — slide outlines.

Single contract layer between the outline generator (studio/outline.py), the
Marp renderer (studio/slides.py), and the artifacts persistence layer
(studio/repository.py).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class Slide(BaseModel):
    """One slide in a deck outline, grounded in source chunks.

    ``source_chunk_ids`` is the anti-hallucination audit trail — every content
    slide must trace back to the chunks it was built from. A pure title/section
    divider slide may legitimately have none.
    """

    title: str
    bullets: list[str] = Field(default_factory=list)
    visual_hint: str | None = None
    source_chunk_ids: list[uuid.UUID] = Field(default_factory=list)


class Outline(BaseModel):
    """A slide-deck outline for a notebook, returned by ``generate_outline``."""

    notebook_id: uuid.UUID
    title: str
    slides: list[Slide] = Field(default_factory=list)
