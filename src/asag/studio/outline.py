"""Slide outline generator — Gemini structured output, grounded in source chunks.

generate_outline(notebook_id, n_slides) fetches coverage chunks, asks the LLM for
a deck outline citing chunks by number, then resolves those numbers back to real
chunk UUIDs (anti-hallucination grounding, mirroring assessment/generators).
"""

from __future__ import annotations

import logging
from pathlib import Path
import uuid

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from asag.assessment.generators.base import numbered_context, resolve_refs
from asag.config import get_settings
from asag.core.llm import structured_output
from asag.core.observability import traced
from asag.models.studio import Outline, Slide
from asag.studio.repository import StudioRepository

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "outline.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# LLM response schema — distinct from the persisted Outline/Slide models       #
# --------------------------------------------------------------------------- #


class _SlideDraft(BaseModel):
    title: str
    bullets: list[str] = []
    visual_hint: str | None = None
    source_refs: list[int] = []


class _OutlineDraft(BaseModel):
    deck_title: str
    slides: list[_SlideDraft]


@traced("studio.generate_outline")
async def generate_outline(
    notebook_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    n_slides: int = 10,
    model: str | None = None,
    coverage_k: int = 30,
) -> Outline:
    """Generate a grounded slide-deck outline for a notebook.

    Args:
        notebook_id: Notebook to draw source chunks from.
        pool:        DB connection pool.
        n_slides:    Target slide count (the model may return a few more or fewer).
        model:       Generator model; defaults to ``ASAG_LLM_GENERATOR``.
        coverage_k:  Max chunks fed to the generator.

    Returns:
        An Outline whose content slides carry resolved ``source_chunk_ids``.

    Raises:
        ValueError: If the notebook has no ingested chunks.
    """
    cfg = get_settings()
    gen_model = model or cfg.asag_llm_generator

    repo = StudioRepository(pool)
    chunks = await repo.fetch_notebook_chunks(notebook_id, limit=coverage_k)
    if not chunks:
        raise ValueError(f"Notebook {notebook_id} has no ingested chunks to build slides from")

    context, ref_map = numbered_context(chunks)
    system = _PROMPT_TEMPLATE.replace("{n_slides}", str(n_slides)).replace("{context}", context)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Produce the deck outline now as JSON."},
    ]

    draft = await structured_output(messages, gen_model, _OutlineDraft)

    slides = [
        Slide(
            title=s.title,
            bullets=s.bullets,
            visual_hint=s.visual_hint,
            source_chunk_ids=resolve_refs(s.source_refs, ref_map),
        )
        for s in draft.slides
    ]
    ungrounded = sum(1 for s in slides if s.bullets and not s.source_chunk_ids)
    if ungrounded:
        # Content slides with no traceable source violate the anti-hallucination
        # rule; surface them for the teacher rather than silently shipping.
        log.warning(
            "generate_outline: %d ungrounded content slide(s) in %s", ungrounded, notebook_id
        )

    log.info("generate_outline: notebook=%s slides=%d", notebook_id, len(slides))
    return Outline(notebook_id=notebook_id, title=draft.deck_title, slides=slides)
