"""Grounding validation — a second LLM pass that checks a question is supported.

validate_grounding(question, chunks) returns False when the question's expected
answer relies on facts not present in its cited chunks. The quiz orchestrator
flags such questions ``needs_review`` so a teacher can fix them before publish.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from asag.core.llm import structured_output
from asag.models.question import Question
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "validation.md").read_text(encoding="utf-8")


class _GroundingVerdict(BaseModel):
    is_grounded: bool
    reasoning: str


def _answer_text(question: Question) -> str:
    """Best-effort human-readable answer for the validation prompt.

    For MCQ we include the *text* of the correct option (not just its letter) —
    otherwise the validator has no claim to check against the sources.
    """
    if "correct_key" in question.answer:
        key = str(question.answer["correct_key"])
        option_text = next((o.text for o in (question.options or []) if o.key == key), "")
        return f"Correct option {key}: {option_text}".strip()
    if "reference" in question.answer:
        return str(question.answer["reference"])
    return ""


async def validate_grounding(
    question: Question,
    chunks: list[ChunkResult],
    *,
    model: str,
) -> bool:
    """Return True if *question* is fully supported by its cited *chunks*.

    Args:
        question: The generated question to verify.
        chunks:   The chunks cited by the question (already filtered to its
                  ``source_chunk_ids``). Empty list → ungrounded by definition.
        model:    LiteLLM model string for the validation pass. Prefer a model
                  distinct from the generator to avoid self-confirmation bias.

    Returns:
        True if grounded; False if cited sources do not support the answer.
    """
    if not chunks:
        return False

    context = "\n\n".join(f"[{i}] {c.content}" for i, c in enumerate(chunks, 1))
    system = (
        _PROMPT_TEMPLATE.replace("{question}", question.stem)
        .replace("{answer}", _answer_text(question))
        .replace("{context}", context)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Return the grounding verdict as JSON."},
    ]

    verdict = await structured_output(messages, model, _GroundingVerdict)
    if not verdict.is_grounded:
        log.info("Ungrounded question: %.60s — %s", question.stem, verdict.reasoning)
    return verdict.is_grounded
