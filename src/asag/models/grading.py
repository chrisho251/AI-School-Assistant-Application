"""Pydantic models for auto-grading — the result a grader returns per answer.

``GradeResult`` is the single contract between graders (assessment/graders/*),
the grading orchestrator (assessment/grading.py), and the ``answers`` table.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GradeResult(BaseModel):
    """The outcome of grading one answer.

    ``score`` is on the question's own scale (1.0 max for MCQ; ``rubric.max_score``
    for short answer). ``needs_human`` is set when a grader cannot produce a
    confident score (e.g. an unregistered/unsupported type) — the orchestrator
    writes a null ``auto_score`` and leaves the answer for the teacher.
    """

    score: float
    max_score: float
    feedback: str = ""
    matched_rubric_items: list[str] = Field(default_factory=list)
    needs_human: bool = False
