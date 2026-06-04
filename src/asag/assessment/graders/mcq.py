"""MCQ grader — deterministic comparison, no LLM call.

grade_mcq(question, response) compares the student's selected option key against
the question's ``answer["correct_key"]``. Case- and whitespace-insensitive.
"""

from __future__ import annotations

import logging
from typing import Any

from asag.models.grading import GradeResult
from asag.models.question import Question

log = logging.getLogger(__name__)

_MAX_SCORE = 1.0


def _selected_key(response: dict[str, Any]) -> str:
    """Pull the chosen option key from a student response payload.

    Accepts ``selected_key`` (canonical) or ``answer`` (lenient alias) so the
    UI/API layer has one less shape to normalise.
    """
    raw = response.get("selected_key", response.get("answer", ""))
    return str(raw).strip().upper()


async def grade_mcq(
    question: Question,
    response: dict[str, Any],
    *,
    model: str | None = None,  # noqa: ARG001 — uniform grader signature; MCQ is deterministic
) -> GradeResult:
    """Grade a single MCQ answer deterministically.

    Args:
        question: The MCQ question; ``answer["correct_key"]`` holds the key.
        response: Student payload, e.g. ``{"selected_key": "B"}``.
        model:    Ignored — present only to match the grader signature.

    Returns:
        ``GradeResult`` with score 1.0 for an exact key match, else 0.0.
    """
    correct = str(question.answer.get("correct_key", "")).strip().upper()
    selected = _selected_key(response)

    if not selected:
        return GradeResult(
            score=0.0, max_score=_MAX_SCORE, feedback="No option selected.", needs_human=False
        )

    is_correct = selected == correct and correct != ""
    feedback = "Correct." if is_correct else f"Incorrect — the correct answer is {correct}."
    log.debug("grade_mcq: selected=%s correct=%s -> %s", selected, correct, is_correct)
    return GradeResult(
        score=_MAX_SCORE if is_correct else 0.0,
        max_score=_MAX_SCORE,
        feedback=feedback,
    )
