"""Unit tests for the short-answer LLM-as-Judge grader — judge mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from asag.assessment.graders.short import _JudgeVerdict, grade_short
from asag.models.question import Question, QuestionType, Rubric, RubricItem


def _short(max_pts: float = 4.0) -> Question:
    return Question(
        type=QuestionType.short,
        stem="Explain photosynthesis.",
        answer={"reference": "Plants convert light to chemical energy."},
        rubric=Rubric(
            items=[
                RubricItem(criterion="mentions light", points=2),
                RubricItem(criterion="mentions energy", points=2),
            ],
            max_score=max_pts,
        ),
    )


async def test_judge_score_passthrough() -> None:
    verdict = _JudgeVerdict(score=3.0, reasoning="partial", matched_rubric_items=["mentions light"])
    with patch(
        "asag.assessment.graders.short.structured_output",
        new=AsyncMock(return_value=verdict),
    ):
        r = await grade_short(_short(), {"text": "Plants use light."}, model="groq/x")
    assert r.score == 3.0
    assert r.max_score == 4.0
    assert r.matched_rubric_items == ["mentions light"]
    assert r.feedback == "partial"


async def test_score_clamped_to_max() -> None:
    verdict = _JudgeVerdict(score=99.0, reasoning="overshot", matched_rubric_items=[])
    with patch(
        "asag.assessment.graders.short.structured_output",
        new=AsyncMock(return_value=verdict),
    ):
        r = await grade_short(_short(), {"text": "x"}, model="groq/x")
    assert r.score == 4.0


async def test_negative_score_clamped_to_zero() -> None:
    verdict = _JudgeVerdict(score=-5.0, reasoning="bug", matched_rubric_items=[])
    with patch(
        "asag.assessment.graders.short.structured_output",
        new=AsyncMock(return_value=verdict),
    ):
        r = await grade_short(_short(), {"text": "x"}, model="groq/x")
    assert r.score == 0.0


async def test_empty_answer_short_circuits_without_llm() -> None:
    judge = AsyncMock()
    with patch("asag.assessment.graders.short.structured_output", new=judge):
        r = await grade_short(_short(), {"text": "   "}, model="groq/x")
    assert r.score == 0.0
    judge.assert_not_awaited()


async def test_no_rubric_falls_back_to_0_4_scale() -> None:
    q = Question(
        type=QuestionType.short,
        stem="Define X.",
        answer={"reference": "X is Y."},
        rubric=None,
    )
    verdict = _JudgeVerdict(score=4.0, reasoning="full", matched_rubric_items=[])
    with patch(
        "asag.assessment.graders.short.structured_output",
        new=AsyncMock(return_value=verdict),
    ):
        r = await grade_short(q, {"text": "X is Y."}, model="groq/x")
    assert r.max_score == 4.0
    assert r.score == 4.0
