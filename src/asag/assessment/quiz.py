"""Quiz generation orchestrator — coverage fetch → generate per type → validate → save.

generate_quiz(notebook_id, config) dispatches to the registered generator for
each requested question type, runs a grounding-validation pass that flags
unsupported questions ``needs_review``, persists the draft, and returns the Quiz.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.assessment import get_generator
from asag.assessment.repository import AssessmentRepository
from asag.assessment.validation import validate_grounding
from asag.config import get_settings
from asag.core.observability import traced
from asag.models.question import Question, Quiz, QuizConfig
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)


async def _flag_ungrounded(
    questions: list[Question],
    chunks: list[ChunkResult],
    *,
    model: str,
) -> None:
    """Run the grounding pass on already-grounded questions; flag failures in place.

    Skips questions the generator already flagged or that have no citations —
    those are review-bound regardless. Runs the remaining checks concurrently.
    """
    by_id = {c.id: c for c in chunks}

    async def _check(q: Question) -> None:
        cited = [by_id[cid] for cid in q.source_chunk_ids if cid in by_id]
        try:
            grounded = await validate_grounding(q, cited, model=model)
        except Exception:
            # Fail safe: a validator outage must not discard generated questions —
            # flag for the teacher instead of aborting the whole quiz.
            log.warning("Grounding check failed for %.60s; flagging review", q.stem, exc_info=True)
            grounded = False
        if not grounded:
            q.needs_review = True

    pending = [q for q in questions if not q.needs_review and q.source_chunk_ids]
    if pending:
        await asyncio.gather(*(_check(q) for q in pending))


@traced("quiz.generate")
async def generate_quiz(
    notebook_id: uuid.UUID,
    config: QuizConfig,
    *,
    created_by: uuid.UUID,
    pool: AsyncConnectionPool,
    model: str | None = None,
    validate_model: str | None = None,
    coverage_k: int = 40,
) -> Quiz:
    """Generate a draft quiz for a notebook and persist it.

    Args:
        notebook_id:    Notebook to draw source chunks from.
        config:         Title, type mix (e.g. ``{mcq: 5, short: 3}``), difficulty.
        created_by:     Teacher creating the quiz (``quizzes.created_by``).
        pool:           DB connection pool.
        model:          Generator model; defaults to ``ASAG_LLM_GENERATOR``.
        validate_model: Grounding-check model; defaults to the judge model
                        (``ASAG_LLM_JUDGE``) so validation is cross-model.
        coverage_k:     Max chunks fed to the generators.

    Returns:
        The saved Quiz (status ``draft``) with its questions; ungrounded questions
        carry ``needs_review=True``.
    """
    cfg = get_settings()
    gen_model = model or cfg.asag_llm_generator
    val_model = validate_model or cfg.asag_llm_judge

    repo = AssessmentRepository(pool)
    chunks = await repo.fetch_notebook_chunks(notebook_id, limit=coverage_k)
    if not chunks:
        raise ValueError(f"Notebook {notebook_id} has no ingested chunks to generate from")

    questions: list[Question] = []
    for qtype, count in config.mix.items():
        if count <= 0:
            continue
        generator = get_generator(qtype)
        produced = await generator(chunks, count, model=gen_model, difficulty=config.difficulty)
        questions.extend(produced)

    await _flag_ungrounded(questions, chunks, model=val_model)

    quiz_id = await repo.save_quiz(notebook_id, config.title, questions, created_by=created_by)
    flagged = sum(1 for q in questions if q.needs_review)
    log.info(
        "generate_quiz: notebook=%s questions=%d needs_review=%d",
        notebook_id,
        len(questions),
        flagged,
    )
    return Quiz(
        id=quiz_id,
        notebook_id=notebook_id,
        title=config.title,
        status="draft",
        questions=questions,
    )
