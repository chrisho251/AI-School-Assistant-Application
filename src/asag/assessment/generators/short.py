"""Short-answer generator — Gemini structured output with grading rubric.

generate_short(chunks, n) returns Question rows of type ``short``, each carrying
a reference answer plus a 0–4 rubric for the LLM-as-Judge grader (Day 7).
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from asag.assessment.generators.base import numbered_context, resolve_refs
from asag.core.llm import structured_output
from asag.models.question import Difficulty, Question, QuestionType, Rubric, RubricItem
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "short.md").read_text(
    encoding="utf-8"
)


class _ShortItem(BaseModel):
    stem: str
    reference_answer: str
    rubric_items: list[RubricItem]
    source_refs: list[int]


class _ShortBatch(BaseModel):
    questions: list[_ShortItem]


def _to_question(
    item: _ShortItem,
    ref_map: dict[int, ChunkResult],
    difficulty: Difficulty,
    with_rubric: bool,
) -> Question:
    """Convert one LLM item to a short-answer Question, flagging ungrounded items."""
    source_chunk_ids = resolve_refs(item.source_refs, ref_map)

    rubric: Rubric | None = None
    if with_rubric and item.rubric_items:
        rubric = Rubric(
            items=item.rubric_items,
            max_score=sum(ri.points for ri in item.rubric_items),
        )

    needs_review = not source_chunk_ids or not item.reference_answer.strip()
    if needs_review:
        log.warning("Short question flagged needs_review: stem=%.60s", item.stem)

    return Question(
        type=QuestionType.short,
        stem=item.stem,
        answer={"reference": item.reference_answer},
        rubric=rubric,
        source_chunk_ids=source_chunk_ids,
        difficulty=difficulty,
        needs_review=needs_review,
    )


async def generate_short(
    chunks: list[ChunkResult],
    n: int,
    *,
    model: str,
    difficulty: Difficulty = Difficulty.medium,
    with_rubric: bool = True,
) -> list[Question]:
    """Generate *n* grounded short-answer questions with rubrics from *chunks*.

    Args:
        chunks:      Source chunks the questions must be grounded in.
        n:           Number of questions to request.
        model:       LiteLLM model string for the generator.
        difficulty:  Target difficulty band.
        with_rubric: When True, attach a 0–4 grading rubric per question.

    Returns:
        Up to *n* short-answer Question objects; ungrounded items are flagged
        ``needs_review`` rather than discarded.
    """
    if not chunks or n <= 0:
        return []

    context, ref_map = numbered_context(chunks)
    system = (
        _PROMPT_TEMPLATE.replace("{n}", str(n))
        .replace("{difficulty}", difficulty.value)
        .replace("{context}", context)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Generate the questions now as JSON."},
    ]

    batch = await structured_output(messages, model, _ShortBatch)
    log.debug("generate_short: requested=%d returned=%d", n, len(batch.questions))
    return [_to_question(item, ref_map, difficulty, with_rubric) for item in batch.questions]
