"""Grader strategy contract — one async callable per question type.

Every grader takes the persisted ``Question`` plus the student's raw ``response``
payload and returns a ``GradeResult``. Deterministic graders (MCQ) ignore
*model*; LLM-as-Judge graders (short) use it as the judge model string. Keeping
the signature uniform lets the orchestrator dispatch by type without special
cases (strategy pattern, see CLAUDE.md §6.5).
"""

from __future__ import annotations

from typing import Any, Protocol

from asag.models.grading import GradeResult
from asag.models.question import Question


class Grader(Protocol):
    """A grader for one question type. ``model`` is the judge model for LLM graders."""

    async def __call__(
        self, question: Question, response: dict[str, Any], *, model: str
    ) -> GradeResult: ...
