"""Quiz endpoints — generate (teacher), list, and get (answer-key omitted).

Generation authorizes notebook ownership under RLS, then delegates to the
``assessment.quiz.generate_quiz`` orchestrator on the service-role pool.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from asag.api.deps import AuthContext, get_db, get_pool, require_teacher, verify_jwt
from asag.assessment.quiz import generate_quiz
from asag.assessment.repository import AssessmentApiRepository
from asag.ingestion.repository import NotebookRepository
from asag.models.api import QuizGenerateRequest, QuizSummary
from asag.models.question import QuizConfig

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("/generate", response_model=QuizSummary, status_code=status.HTTP_201_CREATED)
async def generate(
    body: QuizGenerateRequest,
    auth: AuthContext = Depends(require_teacher),
    db: AsyncConnection = Depends(get_db),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> QuizSummary:
    """Generate a draft quiz from a notebook the calling teacher owns."""
    notebook = await NotebookRepository(db).get_by_id(body.notebook_id)
    if notebook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
    if uuid.UUID(str(notebook["owner_id"])) != auth.user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the notebook owner can generate quizzes"
        )

    config = QuizConfig(title=body.title, mix=body.mix, difficulty=body.difficulty)
    try:
        quiz = await generate_quiz(body.notebook_id, config, created_by=auth.user_id, pool=pool)
    except ValueError as exc:  # e.g. notebook has no ingested chunks
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return QuizSummary(
        id=quiz.id, notebook_id=quiz.notebook_id, title=quiz.title, status=quiz.status
    )


@router.patch("/{quiz_id}/publish", response_model=QuizSummary)
async def publish_quiz(
    quiz_id: uuid.UUID,
    auth: AuthContext = Depends(require_teacher),
    db: AsyncConnection = Depends(get_db),
) -> QuizSummary:
    """Publish a draft quiz so students can attempt it (creator only, via RLS)."""
    repo = AssessmentApiRepository(db)
    if not await repo.set_quiz_status(quiz_id, "published"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found or you are not its creator")
    quiz = await repo.get_quiz(quiz_id)
    assert quiz is not None  # just updated under the same RLS scope
    return QuizSummary(**quiz)


@router.get("/notebook/{notebook_id}", response_model=list[QuizSummary])
async def list_quizzes(
    notebook_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> list[QuizSummary]:
    """List quizzes for a notebook the caller can access (RLS-filtered)."""
    rows = await AssessmentApiRepository(db).list_quizzes(notebook_id)
    return [QuizSummary(**r) for r in rows]


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> dict[str, object]:
    """Return a quiz header plus its questions (without the answer key)."""
    repo = AssessmentApiRepository(db)
    quiz = await repo.get_quiz(quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    questions = await repo.get_quiz_questions(quiz_id)
    return {**quiz, "questions": questions}
