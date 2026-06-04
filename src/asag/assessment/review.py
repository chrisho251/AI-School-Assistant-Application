"""Teacher review + finalisation — override auto-scores, commit final scores.

A teacher reviews an auto-graded attempt, optionally overrides individual answer
scores, then finalises: each answer's ``final_score`` is committed (teacher score
if overridden, else auto score) and the attempt moves to ``finalized``. Only after
finalisation is a score considered official (requirement: teacher checks before
the grade is stored).
"""

from __future__ import annotations

import logging
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.assessment.repository import AssessmentRepository

log = logging.getLogger(__name__)


async def override_answer_score(
    answer_id: uuid.UUID,
    teacher_id: uuid.UUID,
    score: float,
    *,
    pool: AsyncConnectionPool,
    feedback: str | None = None,
) -> None:
    """Record a teacher's score override on one answer.

    Writes ``teacher_score`` / ``teacher_feedback`` and stamps ``updated_by`` for
    audit. Does not change ``final_score`` — that is committed by ``finalize_attempt``.

    Args:
        answer_id:  Answer to override.
        teacher_id: Reviewing teacher (audited as ``updated_by``).
        score:      The teacher's score for this answer.
        pool:       DB connection pool.
        feedback:   Optional teacher feedback shown to the student.
    """
    repo = AssessmentRepository(pool)
    # Fix #2: application-layer ownership guard (Day 9 API will also enforce via RLS).
    await repo.verify_teacher_owns_answer(answer_id, teacher_id)
    await repo.override_answer_score(answer_id, teacher_id, score, feedback)
    log.info("override_answer_score: answer=%s by=%s score=%.2f", answer_id, teacher_id, score)


async def finalize_attempt(
    attempt_id: uuid.UUID,
    teacher_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
) -> float:
    """Commit per-answer ``final_score`` and mark the attempt ``finalized``.

    Args:
        attempt_id: Attempt to finalise.
        teacher_id: Finalising teacher (audited as ``updated_by`` on each answer).
        pool:       DB connection pool.

    Returns:
        The attempt's total final score (sum of per-answer ``final_score``).
    """
    repo = AssessmentRepository(pool)
    # Fix #2: application-layer ownership guard.
    await repo.verify_teacher_owns_attempt(attempt_id, teacher_id)
    total = await repo.finalize_attempt(attempt_id, teacher_id)
    log.info("finalize_attempt: attempt=%s by=%s total=%.2f", attempt_id, teacher_id, total)
    return total
