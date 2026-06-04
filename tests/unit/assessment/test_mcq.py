"""Unit tests for MCQ generation — _to_question grounding + validation logic.

Pure-function tests: no LLM, no DB. Covers the needs_review heuristics that
guard grounding and distractor quality.
"""

from __future__ import annotations

import uuid

from asag.assessment.generators.base import numbered_context
from asag.assessment.generators.mcq import _MCQItem, _to_question
from asag.models.question import Difficulty, MCQOption, QuestionType
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


def _opts(*texts: str) -> list[MCQOption]:
    keys = ["A", "B", "C", "D"]
    return [MCQOption(key=k, text=t) for k, t in zip(keys, texts, strict=False)]


def _item(**over: object) -> _MCQItem:
    base = {
        "stem": "What is X?",
        "options": _opts("one", "two", "three", "four"),
        "correct_key": "B",
        "explanation": "because two",
        "source_refs": [1],
    }
    base.update(over)
    return _MCQItem(**base)  # type: ignore[arg-type]


def test_valid_mcq_is_grounded_and_clean() -> None:
    chunks = [_chunk()]
    _, ref_map = numbered_context(chunks)
    q = _to_question(_item(), ref_map, Difficulty.medium)

    assert q.type is QuestionType.mcq
    assert q.needs_review is False
    assert q.source_chunk_ids == [chunks[0].id]
    assert q.answer == {"correct_key": "B", "explanation": "because two"}
    assert q.difficulty is Difficulty.medium


def test_ungrounded_when_refs_out_of_range() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(_item(source_refs=[99]), ref_map, Difficulty.easy)
    assert q.source_chunk_ids == []
    assert q.needs_review is True


def test_duplicate_distractor_flags_review() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(
        _item(options=_opts("same", "same", "three", "four")), ref_map, Difficulty.medium
    )
    assert q.needs_review is True


def test_correct_key_not_in_options_flags_review() -> None:
    _, ref_map = numbered_context([_chunk()])
    q = _to_question(_item(correct_key="Z"), ref_map, Difficulty.medium)
    assert q.needs_review is True


def test_wrong_option_count_flags_review() -> None:
    _, ref_map = numbered_context([_chunk()])
    three = [MCQOption(key=k, text=t) for k, t in zip("ABC", ["a", "b", "c"], strict=True)]
    q = _to_question(_item(options=three), ref_map, Difficulty.medium)
    assert q.needs_review is True
