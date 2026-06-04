"""Data access for quiz generation — fetch coverage chunks, persist quiz drafts.

All SQL for the assessment domain lives here; services (quiz.py) call these
methods and never write SQL inline (repository pattern, see CLAUDE.md §6.5).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.models.question import (
    Difficulty,
    MCQOption,
    Question,
    QuestionType,
    Rubric,
)
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)


@dataclass
class AnswerToGrade:
    """One student answer paired with the question it responds to, for grading."""

    answer_id: uuid.UUID
    response: dict[str, Any]
    question: Question


def _row_to_question(d: dict[str, Any]) -> Question:
    """Reconstruct a Question from a ``questions`` row dict (jsonb already parsed)."""
    options = d.get("options")
    rubric = d.get("rubric")
    return Question(
        type=QuestionType(d["type"]),
        stem=str(d["stem"]),
        options=[MCQOption(**o) for o in options] if options else None,
        answer=d.get("answer") or {},
        rubric=Rubric.model_validate(rubric) if rubric else None,
        source_chunk_ids=[uuid.UUID(str(c)) for c in (d.get("source_chunk_ids") or [])],
        difficulty=Difficulty(d.get("difficulty_level") or "medium"),
        needs_review=bool(d.get("needs_review")),
    )


def _row_to_chunk(d: dict[str, Any]) -> ChunkResult:
    """Build a ChunkResult from a psycopg row dict (score is irrelevant here)."""
    return ChunkResult(
        id=uuid.UUID(str(d["id"])),
        source_id=uuid.UUID(str(d["source_id"])),
        notebook_id=uuid.UUID(str(d["notebook_id"])),
        content=str(d["content"]),
        content_type=str(d["content_type"]),
        page_number=int(d["page_number"]) if d["page_number"] is not None else None,
        metadata=d["metadata"] if isinstance(d["metadata"], dict) else {},
    )


class AssessmentRepository:
    """Postgres access for the assessment domain.

    Args:
        pool: Async connection pool. RLS context (if any) is set by the caller;
              POC quiz generation runs as a server-side task with the service role.
    """

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def fetch_notebook_chunks(
        self, notebook_id: uuid.UUID, *, limit: int = 40
    ) -> list[ChunkResult]:
        """Return up to *limit* chunks for a notebook, ordered for broad coverage.

        Ordering by (source_id, ordinal) keeps each source's chunks contiguous so
        a truncated set still spans whole sections rather than random fragments.
        """
        sql = """
            SELECT id, source_id, notebook_id, content, content_type, page_number, metadata
            FROM chunks
            WHERE notebook_id = %s
              AND content IS NOT NULL
            ORDER BY source_id, ordinal
            LIMIT %s
        """
        async with self.pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (str(notebook_id), limit))
            cols = [c.name for c in cur.description]  # type: ignore[union-attr]
            rows = await cur.fetchall()
        return [_row_to_chunk(dict(zip(cols, row, strict=False))) for row in rows]

    async def save_quiz(
        self,
        notebook_id: uuid.UUID,
        title: str,
        questions: list[Question],
        *,
        created_by: uuid.UUID,
        status: str = "draft",
    ) -> uuid.UUID:
        """Insert a quiz and its questions in one transaction; return the quiz id."""
        quiz_id = uuid.uuid4()
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO quizzes (id, notebook_id, created_by, title, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (str(quiz_id), str(notebook_id), str(created_by), title, status),
            )
            for ordinal, q in enumerate(questions):
                await conn.execute(
                    """INSERT INTO questions
                       (quiz_id, ordinal, type, stem, options, answer, rubric,
                        source_chunk_ids, difficulty_level, needs_review)
                       VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                               %s::uuid[], %s, %s)""",
                    (
                        str(quiz_id),
                        ordinal,
                        q.type.value,
                        q.stem,
                        json.dumps([o.model_dump() for o in q.options])
                        if q.options is not None
                        else None,
                        json.dumps(q.answer),
                        q.rubric.model_dump_json() if q.rubric is not None else None,
                        [str(cid) for cid in q.source_chunk_ids],
                        q.difficulty.value,
                        q.needs_review,
                    ),
                )
        log.debug("save_quiz: quiz=%s questions=%d", quiz_id, len(questions))
        return quiz_id

    # ----------------------------------------------------------------- #
    # Grading (Session 7A)                                              #
    # ----------------------------------------------------------------- #

    async def fetch_attempt_answers(self, attempt_id: uuid.UUID) -> list[AnswerToGrade]:
        """Return every answer in *attempt_id* paired with its question, in order."""
        sql = """
            SELECT a.id AS answer_id, a.response,
                   q.type, q.stem, q.options, q.answer, q.rubric,
                   q.source_chunk_ids, q.difficulty_level, q.needs_review
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            WHERE a.attempt_id = %s
            ORDER BY q.ordinal
        """
        async with self.pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (str(attempt_id),))
            cols = [c.name for c in cur.description]  # type: ignore[union-attr]
            rows = await cur.fetchall()

        tasks: list[AnswerToGrade] = []
        for row in rows:
            d = dict(zip(cols, row, strict=False))
            tasks.append(
                AnswerToGrade(
                    answer_id=uuid.UUID(str(d["answer_id"])),
                    response=d["response"] if isinstance(d["response"], dict) else {},
                    question=_row_to_question(d),
                )
            )
        return tasks

    async def commit_grade_results(
        self,
        attempt_id: uuid.UUID,
        grades: list[tuple[uuid.UUID, float | None, str]],
    ) -> None:
        """Batch-write auto-grades and mark the attempt ``graded`` in one transaction.

        Fix #1: coalescing N pool round-trips into one transaction avoids N separate
        autocommits and cuts DB latency proportionally.

        Args:
            attempt_id: The attempt being graded.
            grades:     List of ``(answer_id, score | None, feedback)``. A ``None``
                        score means ``needs_human``; persisted as NULL so the teacher
                        can supply a score during review.
        """
        async with self.pool.connection() as conn, conn.transaction():
            for answer_id, score, feedback in grades:
                await conn.execute(
                    "UPDATE answers SET auto_score = %s, auto_feedback = %s, "
                    "updated_at = now() WHERE id = %s",
                    (score, feedback, str(answer_id)),
                )
            await conn.execute(
                "UPDATE attempts SET status = 'graded' WHERE id = %s",
                (str(attempt_id),),
            )
        log.debug("commit_grade_results: attempt=%s answers=%d", attempt_id, len(grades))

    async def set_attempt_status(self, attempt_id: uuid.UUID, status: str) -> None:
        """Transition an attempt to *status* (e.g. ``submitted``, ``graded``)."""
        await self._execute(
            "UPDATE attempts SET status = %s WHERE id = %s",
            (status, str(attempt_id)),
        )

    # ----------------------------------------------------------------- #
    # Teacher review + finalisation (Session 7B)                        #
    # ----------------------------------------------------------------- #

    async def verify_teacher_owns_attempt(
        self, attempt_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> None:
        """Raise PermissionError if *teacher_id* is not the quiz creator for *attempt_id*.

        Fix #2 (application-layer ownership guard): the Day 9 API enforces this via
        RLS + JWT, but the service layer must also check so scripts or future callers
        that bypass the API cannot tamper with other teachers' attempts.
        """
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM attempts a"
                "  JOIN quizzes q ON q.id = a.quiz_id"
                "  WHERE a.id = %s AND q.created_by = %s"
                ")",
                (str(attempt_id), str(teacher_id)),
            )
            row = await cur.fetchone()
        if not (row and row[0]):
            raise PermissionError(
                f"teacher {teacher_id} does not own the quiz for attempt {attempt_id}"
            )

    async def verify_teacher_owns_answer(self, answer_id: uuid.UUID, teacher_id: uuid.UUID) -> None:
        """Raise PermissionError if *teacher_id* is not the quiz creator for *answer_id*."""
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM answers ans"
                "  JOIN attempts a ON a.id = ans.attempt_id"
                "  JOIN quizzes q ON q.id = a.quiz_id"
                "  WHERE ans.id = %s AND q.created_by = %s"
                ")",
                (str(answer_id), str(teacher_id)),
            )
            row = await cur.fetchone()
        if not (row and row[0]):
            raise PermissionError(
                f"teacher {teacher_id} does not own the quiz for answer {answer_id}"
            )

    async def override_answer_score(
        self,
        answer_id: uuid.UUID,
        teacher_id: uuid.UUID,
        score: float,
        feedback: str | None,
    ) -> None:
        """Record a teacher override on one answer (audited via ``updated_by``)."""
        await self._execute(
            "UPDATE answers SET teacher_score = %s, teacher_feedback = %s, "
            "updated_by = %s, updated_at = now() WHERE id = %s",
            (score, feedback, str(teacher_id), str(answer_id)),
        )

    async def finalize_attempt(self, attempt_id: uuid.UUID, teacher_id: uuid.UUID) -> float:
        """Commit ``final_score`` per answer and mark the attempt finalized.

        Each answer's ``final_score`` = teacher override if present, else the auto
        score. Sets ``finalized_at`` on every answer and the attempt status to
        ``finalized``. Returns the attempt's total final score.

        Raises:
            ValueError: If any answer still has no score (auto_score IS NULL AND
                teacher_score IS NULL). The teacher must override those answers
                before finalising — fix #3.
        """
        # Fix #3: refuse to finalise when any answer was flagged needs_human and
        # the teacher has not yet supplied a score. An answer with both scores NULL
        # would silently produce final_score = NULL and undercount the total.
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM answers "
                "WHERE attempt_id = %s AND auto_score IS NULL AND teacher_score IS NULL",
                (str(attempt_id),),
            )
            row = await cur.fetchone()
        ungraded = int(row[0]) if row else 0
        if ungraded > 0:
            raise ValueError(
                f"Cannot finalise attempt {attempt_id}: {ungraded} answer(s) have no score. "
                "Call override_answer_score() for each ungraded answer first."
            )

        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute(
                "UPDATE answers "
                "SET final_score = COALESCE(teacher_score, auto_score), "
                "    finalized_at = now(), updated_by = %s "
                "WHERE attempt_id = %s",
                (str(teacher_id), str(attempt_id)),
            )
            await conn.execute(
                "UPDATE attempts SET status = 'finalized' WHERE id = %s",
                (str(attempt_id),),
            )
            cur = await conn.execute(
                "SELECT COALESCE(SUM(final_score), 0) FROM answers WHERE attempt_id = %s",
                (str(attempt_id),),
            )
            row = await cur.fetchone()
        total = float(row[0]) if row and row[0] is not None else 0.0
        log.debug("finalize_attempt: attempt=%s total=%.2f", attempt_id, total)
        return total

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        """Run a single autocommit statement on a pooled connection."""
        async with self.pool.connection() as conn:
            await conn.execute(sql, params)
