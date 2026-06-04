"""Attempt lifecycle — start, submit (triggers async grading), get, finalize.

Student-facing routes run under RLS so a student can only touch their own attempts;
finalization is teacher-only and additionally guarded at the service layer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from asag.api.deps import (
    AuthContext,
    get_db,
    get_pool,
    require_teacher,
    rls_connection,
    verify_jwt,
)
from asag.assessment.grading import grade_attempt
from asag.assessment.repository import AssessmentApiRepository
from asag.assessment.review import finalize_attempt, override_answer_score
from asag.core.queue import BackgroundTaskQueue
from asag.models.api import (
    AnswerReview,
    AnswerScoreOverride,
    AttemptOut,
    AttemptStart,
    AttemptSubmit,
)

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.post("/start", response_model=AttemptOut, status_code=status.HTTP_201_CREATED)
async def start_attempt(
    body: AttemptStart,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> AttemptOut:
    """Start an attempt on a published quiz for the calling student."""
    repo = AssessmentApiRepository(db)
    quiz = await repo.get_quiz(body.quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    if quiz["status"] != "published":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quiz is not published")

    row = await repo.create_attempt(body.quiz_id, auth.user_id)
    return AttemptOut(**row)


@router.post("/{attempt_id}/submit", response_model=AttemptOut)
async def submit_attempt(
    attempt_id: uuid.UUID,
    body: AttemptSubmit,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(verify_jwt),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> AttemptOut:
    """Submit answers, lock the attempt, and queue auto-grading.

    The RLS transaction is opened and committed *inside* the handler (not via the
    ``get_db`` dependency) so the ``attempts`` row lock is released before the
    background grader runs — otherwise the still-open request transaction would
    deadlock the grader against its own ``UPDATE attempts``.
    """
    async with rls_connection(pool, auth) as conn:
        repo = AssessmentApiRepository(conn)
        attempt = await repo.get_attempt(attempt_id)
        if attempt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
        if uuid.UUID(str(attempt["student_id"])) != auth.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your attempt")
        if attempt["status"] != "in_progress":
            raise HTTPException(status.HTTP_409_CONFLICT, "Attempt already submitted")
        await repo.submit_answers(attempt_id, [(a.question_id, a.response) for a in body.answers])
        quiz_id = uuid.UUID(str(attempt["quiz_id"]))

    # Transaction committed above; grading runs as the service role after the response.
    BackgroundTaskQueue(background_tasks).enqueue(grade_attempt, attempt_id, pool=pool)

    return AttemptOut(id=attempt_id, quiz_id=quiz_id, student_id=auth.user_id, status="submitted")


@router.get("/{attempt_id}", response_model=AttemptOut)
async def get_attempt(
    attempt_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> AttemptOut:
    """Fetch an attempt the caller owns (student) or created the quiz for (teacher)."""
    attempt = await AssessmentApiRepository(db).get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return AttemptOut(**attempt)


@router.get("/quiz/{quiz_id}", response_model=list[AttemptOut])
async def list_attempts_for_quiz(
    quiz_id: uuid.UUID,
    auth: AuthContext = Depends(require_teacher),
    db: AsyncConnection = Depends(get_db),
) -> list[AttemptOut]:
    """List attempts on a quiz for review (RLS limits to the quiz's creator)."""
    rows = await AssessmentApiRepository(db).list_attempts_by_quiz(quiz_id)
    return [AttemptOut(**r) for r in rows]


@router.get("/{attempt_id}/answers", response_model=list[AnswerReview])
async def list_attempt_answers(
    attempt_id: uuid.UUID,
    auth: AuthContext = Depends(require_teacher),
    db: AsyncConnection = Depends(get_db),
) -> list[AnswerReview]:
    """Return an attempt's answers with scores for the teacher review screen.

    Teacher-only: this exposes provisional ``auto_score`` / ``teacher_score`` before
    finalisation, which students must not see (they get their grade only after the
    teacher finalises — a separate Day 11 student endpoint will gate on that).
    RLS additionally restricts the rows to the quiz the teacher created.
    """
    rows = await AssessmentApiRepository(db).get_attempt_answers_review(attempt_id)
    return [AnswerReview(**r) for r in rows]


@router.patch("/{attempt_id}/answers/{answer_id}/score")
async def override_score(
    attempt_id: uuid.UUID,
    answer_id: uuid.UUID,
    body: AnswerScoreOverride,
    auth: AuthContext = Depends(require_teacher),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict[str, str]:
    """Override one answer's score; only the quiz creator may call this."""
    try:
        await override_answer_score(
            answer_id, auth.user_id, body.score, pool=pool, feedback=body.feedback
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"status": "ok"}


@router.post("/{attempt_id}/finalize")
async def finalize(
    attempt_id: uuid.UUID,
    auth: AuthContext = Depends(require_teacher),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict[str, float]:
    """Commit final scores for an attempt; only the quiz creator may call this."""
    try:
        total = await finalize_attempt(attempt_id, auth.user_id, pool=pool)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:  # ungraded answers remain
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"total_score": total}
