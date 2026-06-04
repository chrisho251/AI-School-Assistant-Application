"""Auto-grading orchestrator — grade every answer in an attempt by question type.

grade_attempt(attempt_id) fetches the attempt's answers, dispatches each to its
registered grader (MCQ deterministic, short LLM-as-Judge), writes ``auto_score`` +
``auto_feedback``, and transitions the attempt to ``graded``. Importing this module
ensures the grader registry is populated.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.assessment import get_grader
import asag.assessment.graders  # noqa: F401  — registers graders into the registry
from asag.assessment.repository import AnswerToGrade, AssessmentRepository
from asag.config import get_settings
from asag.core.observability import traced
from asag.models.grading import GradeResult

log = logging.getLogger(__name__)

# Fix #4: cap concurrent LLM judge calls to avoid 429 bursts on free-tier Groq.
# Deterministic graders (MCQ) acquire and release the semaphore immediately, so
# only LLM-backed graders actually throttle.
_LLM_CONCURRENCY = 5


async def _grade_one(task: AnswerToGrade, *, model: str) -> GradeResult:
    """Grade a single answer via its type's registered grader.

    An unregistered type, or a grader that raises, yields ``needs_human=True``
    with a null score rather than aborting the whole attempt.
    """
    try:
        grader = get_grader(task.question.type)
    except KeyError:
        log.warning("No grader for type %s — flagging for human", task.question.type)
        return GradeResult(score=0.0, max_score=0.0, needs_human=True, feedback="No auto-grader.")

    try:
        return await grader(task.question, task.response, model=model)
    except Exception:
        log.warning(
            "Grader failed for answer %s; flagging for human", task.answer_id, exc_info=True
        )
        return GradeResult(
            score=0.0, max_score=0.0, needs_human=True, feedback="Auto-grading failed."
        )


@traced("grade.attempt")
async def grade_attempt(
    attempt_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    model: str | None = None,
) -> dict[uuid.UUID, GradeResult]:
    """Auto-grade every answer in an attempt and mark it ``graded``.

    Args:
        attempt_id: Attempt to grade.
        pool:       DB connection pool (grading runs server-side; no RLS context).
        model:      Judge model for LLM-graded types; defaults to ``ASAG_LLM_JUDGE``.
                    Deterministic graders ignore it.

    Returns:
        Map of answer id → ``GradeResult``. Answers whose grader set
        ``needs_human`` get a null ``auto_score`` persisted.
    """
    judge_model = model or get_settings().asag_llm_judge
    repo = AssessmentRepository(pool)

    tasks = await repo.fetch_attempt_answers(attempt_id)
    if not tasks:
        log.info("grade_attempt: attempt=%s has no answers", attempt_id)
        await repo.set_attempt_status(attempt_id, "graded")
        return {}

    # Fix #4: semaphore scoped to this event-loop call, not module-level.
    sem = asyncio.Semaphore(_LLM_CONCURRENCY)

    async def _guarded(t: AnswerToGrade) -> GradeResult:
        async with sem:
            return await _grade_one(t, model=judge_model)

    results = await asyncio.gather(*(_guarded(t) for t in tasks))

    # Fix #1: single transaction instead of N separate pool round-trips.
    grades = [
        (t.answer_id, None if r.needs_human else r.score, r.feedback)
        for t, r in zip(tasks, results, strict=True)
    ]
    await repo.commit_grade_results(attempt_id, grades)

    flagged = sum(1 for r in results if r.needs_human)
    log.info(
        "grade_attempt: attempt=%s graded=%d needs_human=%d", attempt_id, len(results), flagged
    )
    return {t.answer_id: r for t, r in zip(tasks, results, strict=True)}
