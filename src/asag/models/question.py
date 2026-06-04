"""Pydantic models for quiz generation — questions, options, rubrics, quiz config.

These are the single contract layer between generators (assessment/generators/*),
the persistence layer (assessment/repository.py), and the DB `questions` table.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    """Question types. POC generates ``mcq`` + ``short``; the rest are extension hooks."""

    mcq = "mcq"
    short = "short"
    essay = "essay"  # extension hook — no generator registered in POC
    code = "code"  # extension hook — no generator registered in POC


class Difficulty(StrEnum):
    """Target difficulty band requested from the generator."""

    easy = "easy"
    medium = "medium"
    hard = "hard"


class MCQOption(BaseModel):
    """One multiple-choice option keyed by a letter (``A``..``D``)."""

    key: str
    text: str


class RubricItem(BaseModel):
    """A single scoring criterion for a short/essay answer."""

    criterion: str
    points: float


class Rubric(BaseModel):
    """Scoring rubric for non-deterministic question types.

    ``max_score`` is the sum of all item points; the LLM judge (Day 7) scores
    against ``items`` and clamps to ``max_score``.
    """

    items: list[RubricItem] = Field(default_factory=list)
    max_score: float


class Question(BaseModel):
    """A generated quiz question, grounded in source chunks.

    The ``answer`` payload shape depends on ``type``:
      - ``mcq``:   ``{"correct_key": "B", "explanation": "..."}``
      - ``short``: ``{"reference": "<reference answer text>"}``

    ``needs_review`` is set by the generator (malformed output) or the grounding
    validation pass (answer not supported by cited chunks).
    """

    type: QuestionType
    stem: str
    options: list[MCQOption] | None = None
    answer: dict[str, Any] = Field(default_factory=dict)
    rubric: Rubric | None = None
    source_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    difficulty: Difficulty = Difficulty.medium
    needs_review: bool = False


class QuizConfig(BaseModel):
    """Request spec for ``generate_quiz`` — how many of each type and what difficulty."""

    title: str
    mix: dict[QuestionType, int] = Field(default_factory=dict)
    difficulty: Difficulty = Difficulty.medium

    @property
    def total(self) -> int:
        """Total questions requested across all types."""
        return sum(self.mix.values())


class Quiz(BaseModel):
    """A generated quiz draft with its questions, returned by ``generate_quiz``."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    status: str = "draft"
    questions: list[Question] = Field(default_factory=list)
