"""Unit tests for the deterministic MCQ grader — no LLM, pure comparison."""

from __future__ import annotations

from asag.assessment.graders.mcq import grade_mcq
from asag.models.question import MCQOption, Question, QuestionType


def _mcq(correct: str = "B") -> Question:
    return Question(
        type=QuestionType.mcq,
        stem="Pick one.",
        options=[MCQOption(key=k, text=k) for k in "ABCD"],
        answer={"correct_key": correct, "explanation": "because"},
    )


async def test_correct_key_scores_full() -> None:
    r = await grade_mcq(_mcq("B"), {"selected_key": "B"})
    assert r.score == 1.0
    assert r.max_score == 1.0
    assert r.needs_human is False


async def test_wrong_key_scores_zero() -> None:
    r = await grade_mcq(_mcq("B"), {"selected_key": "C"})
    assert r.score == 0.0
    assert "correct answer is B" in r.feedback


async def test_case_and_whitespace_insensitive() -> None:
    r = await grade_mcq(_mcq("B"), {"selected_key": " b "})
    assert r.score == 1.0


async def test_answer_alias_accepted() -> None:
    r = await grade_mcq(_mcq("A"), {"answer": "A"})
    assert r.score == 1.0


async def test_no_selection_scores_zero() -> None:
    r = await grade_mcq(_mcq("B"), {})
    assert r.score == 0.0
    assert "No option" in r.feedback
