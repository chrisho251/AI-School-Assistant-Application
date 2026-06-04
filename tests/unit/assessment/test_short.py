"""Unit tests for short-answer generation — _to_question rubric + grounding logic."""

from __future__ import annotations

import uuid

from asag.assessment.generators.base import numbered_context
from asag.assessment.generators.short import _ShortItem, _to_question
from asag.models.question import Difficulty, QuestionType, RubricItem
from asag.rag.retriever import ChunkResult


def _chunk(content: str = "x") -> ChunkResult:
    return ChunkResult(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        content=content,
        content_type="text",
        page_number=None,
    )


def _item(**over: object) -> _ShortItem:
    base = {
        "stem": "Explain X.",
        "reference_answer": "X is a thing that does Y.",
        "rubric_items": [
            RubricItem(criterion="mentions X", points=2),
            RubricItem(criterion="mentions Y", points=2),
        ],
        "source_refs": [1],
    }
    base.update(over)
    return _ShortItem(**base)  # type: ignore[arg-type]


def test_valid_short_builds_rubric_with_summed_max() -> None:
    chunks = [_chunk()]
    _, ref_map = numbered_context(chunks)
    q = _to_question(_item(), ref_map, Difficulty.medium, with_rubric=True)

    assert q.type is QuestionType.short
    assert q.needs_review is False
    assert q.answer == {"reference": "X is a thing that does Y."}
    assert q.rubric is not None
    assert q.rubric.max_score == 4.0
    assert len(q.rubric.items) == 2


def test_with_rubric_false_omits_rubric() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(_item(), ref_map, Difficulty.medium, with_rubric=False)
    assert q.rubric is None


def test_ungrounded_short_flags_review() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(_item(source_refs=[42]), ref_map, Difficulty.hard, with_rubric=True)
    assert q.source_chunk_ids == []
    assert q.needs_review is True


def test_empty_reference_flags_review() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(_item(reference_answer="   "), ref_map, Difficulty.medium, with_rubric=True)
    assert q.needs_review is True
