"""MCQ generator — Gemini structured output, grounded in source chunks.

generate_mcq(chunks, n) returns validated Question rows. Each question's
source_chunk_ids are resolved from model-cited reference numbers (never raw
UUIDs), and malformed items are flagged needs_review rather than dropped.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from asag.assessment.generators.base import numbered_context, resolve_refs
from asag.core.llm import structured_output
from asag.models.question import Difficulty, MCQOption, Question, QuestionType
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "mcq.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# LLM response schema — distinct from the persisted Question model            #
# --------------------------------------------------------------------------- #


class _MCQItem(BaseModel):
    stem: str
    options: list[MCQOption]
    correct_key: str
    explanation: str
    source_refs: list[int]


class _MCQBatch(BaseModel):
    questions: list[_MCQItem]


def _to_question(
    item: _MCQItem, ref_map: dict[int, ChunkResult], difficulty: Difficulty
) -> Question:
    """Convert one LLM item to a Question, flagging malformed output for review."""
    source_chunk_ids = resolve_refs(item.source_refs, ref_map)

    keys = [o.key.strip().upper() for o in item.options]
    texts = [o.text.strip().lower() for o in item.options]

    needs_review = (
        not source_chunk_ids  # ungrounded
        or len(item.options) != 4  # not a 4-option MCQ
        or len(set(keys)) != len(keys)  # duplicate option keys
        or len(set(texts)) != len(texts)  # duplicate distractors
        or item.correct_key.strip().upper() not in keys  # correct answer not among options
    )
    if needs_review:
        log.warning("MCQ flagged needs_review: stem=%.60s", item.stem)

    return Question(
        type=QuestionType.mcq,
        stem=item.stem,
        options=item.options,
        answer={"correct_key": item.correct_key, "explanation": item.explanation},
        source_chunk_ids=source_chunk_ids,
        difficulty=difficulty,
        needs_review=needs_review,
    )


async def generate_mcq(
    chunks: list[ChunkResult],
    n: int,
    *,
    model: str,
    difficulty: Difficulty = Difficulty.medium,
) -> list[Question]:
    """Generate *n* grounded MCQ questions from *chunks*.

    Args:
        chunks:     Source chunks the questions must be grounded in.
        n:          Number of questions to request.
        model:      LiteLLM model string for the generator.
        difficulty: Target difficulty band.

    Returns:
        Up to *n* Question objects (the model may return fewer). Malformed
        items are flagged ``needs_review`` rather than discarded.
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

    batch = await structured_output(messages, model, _MCQBatch)
    log.debug("generate_mcq: requested=%d returned=%d", n, len(batch.questions))
    return [_to_question(item, ref_map, difficulty) for item in batch.questions]
