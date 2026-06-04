"""Short-answer grader — LLM-as-Judge against the rubric + reference answer.

grade_short(question, response, *, model) runs the judge model (distinct from the
generator — anti-bias, see CLAUDE.md §2) and returns a rubric-clamped score. The
judge never sees the source chunks; it grades strictly against the rubric and the
reference answer the generator already grounded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from asag.core.llm import structured_output
from asag.models.grading import GradeResult
from asag.models.question import Question

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "grader_short.md").read_text(
    encoding="utf-8"
)


class _JudgeVerdict(BaseModel):
    score: float
    reasoning: str
    matched_rubric_items: list[str]


def _student_text(response: dict[str, Any]) -> str:
    """Extract the student's free-text answer from the response payload."""
    return str(response.get("text", response.get("answer", ""))).strip()


def _render_rubric(question: Question) -> tuple[str, float]:
    """Return a human-readable rubric block plus its max score.

    Falls back to a single 0–4 band when the question carries no rubric, so the
    judge always has a defined scale to grade against.
    """
    if question.rubric is not None and question.rubric.items:
        lines = [f"- ({ri.points} pts) {ri.criterion}" for ri in question.rubric.items]
        return "\n".join(lines), question.rubric.max_score
    return "- (4 pts) Answer is correct and complete per the reference answer.", 4.0


async def grade_short(
    question: Question,
    response: dict[str, Any],
    *,
    model: str,
) -> GradeResult:
    """Grade a short-answer response with an LLM judge.

    Args:
        question: The short question; ``answer["reference"]`` + ``rubric`` drive grading.
        response: Student payload, e.g. ``{"text": "..."}``.
        model:    Judge model string (``cfg.asag_llm_judge``) — must differ from
                  the generator model to avoid self-preference bias.

    Returns:
        ``GradeResult`` with ``score`` clamped to ``[0, max_score]``. An empty
        student answer short-circuits to score 0 without an LLM call.
    """
    student = _student_text(response)
    rubric_text, max_score = _render_rubric(question)

    if not student:
        return GradeResult(score=0.0, max_score=max_score, feedback="No answer provided.")

    reference = str(question.answer.get("reference", ""))
    system = (
        _PROMPT_TEMPLATE.replace("{question}", question.stem)
        .replace("{reference}", reference)
        .replace("{rubric}", rubric_text)
        .replace("{student_answer}", student)
        .replace("{max_score}", str(max_score))
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Grade the answer now and return the verdict as JSON."},
    ]

    verdict = await structured_output(messages, model, _JudgeVerdict)
    # Clamp defensively: the judge is instructed to stay in range, but a stray
    # out-of-band score must never poison auto_score / final_score downstream.
    score = max(0.0, min(verdict.score, max_score))
    log.debug("grade_short: raw=%.2f clamped=%.2f/%.2f", verdict.score, score, max_score)
    return GradeResult(
        score=score,
        max_score=max_score,
        feedback=verdict.reasoning,
        matched_rubric_items=verdict.matched_rubric_items,
    )
