"""Pydantic request/response models for the FastAPI surface.

These are the API's wire contract — distinct from domain models so the HTTP shape
can evolve independently of internal types.
"""

from __future__ import annotations

from typing import Any
import uuid

from pydantic import BaseModel, Field

from asag.models.question import Difficulty, QuestionType

# --------------------------------------------------------------------------- #
# Notebooks                                                                    #
# --------------------------------------------------------------------------- #


class NotebookCreate(BaseModel):
    """Payload to create a notebook under a class the caller owns/teaches."""

    class_id: uuid.UUID
    title: str
    subject: str | None = None
    description: str | None = None


class NotebookOut(BaseModel):
    """A notebook row returned to the client."""

    id: uuid.UUID
    class_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    subject: str | None = None
    description: str | None = None


# --------------------------------------------------------------------------- #
# Sources                                                                      #
# --------------------------------------------------------------------------- #


class SourceOut(BaseModel):
    """A source row, including its ingestion status for polling."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    source_type: str
    original_filename: str
    storage_url: str
    ingestion_status: str


# --------------------------------------------------------------------------- #
# Quizzes                                                                      #
# --------------------------------------------------------------------------- #


class QuizGenerateRequest(BaseModel):
    """Request to generate a draft quiz from a notebook's chunks."""

    notebook_id: uuid.UUID
    title: str
    mix: dict[QuestionType, int] = Field(default_factory=lambda: {QuestionType.mcq: 5})
    difficulty: Difficulty = Difficulty.medium


class QuizSummary(BaseModel):
    """Lightweight quiz row for list endpoints."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    status: str


# --------------------------------------------------------------------------- #
# Attempts                                                                     #
# --------------------------------------------------------------------------- #


class AttemptStart(BaseModel):
    """Request to start an attempt on a published quiz."""

    quiz_id: uuid.UUID


class AnswerSubmission(BaseModel):
    """One answer in a submission — ``response`` shape depends on question type."""

    question_id: uuid.UUID
    response: dict[str, Any]


class AttemptSubmit(BaseModel):
    """Final submission: all answers for an in-progress attempt."""

    answers: list[AnswerSubmission]


class AttemptOut(BaseModel):
    """An attempt's state, returned after start/submit/get."""

    id: uuid.UUID
    quiz_id: uuid.UUID
    student_id: uuid.UUID
    status: str


class ProctorEvent(BaseModel):
    """A single browser-lockdown event reported during an attempt."""

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Teacher review                                                               #
# --------------------------------------------------------------------------- #


class AnswerReview(BaseModel):
    """One answer with its question and all score columns, for teacher review."""

    answer_id: uuid.UUID
    question_id: uuid.UUID
    ordinal: int
    type: QuestionType
    stem: str
    response: dict[str, Any] = Field(default_factory=dict)
    auto_score: float | None = None
    auto_feedback: str | None = None
    teacher_score: float | None = None
    teacher_feedback: str | None = None
    final_score: float | None = None


class AnswerScoreOverride(BaseModel):
    """Teacher override for one answer's score (committed at finalisation)."""

    score: float
    feedback: str | None = None
