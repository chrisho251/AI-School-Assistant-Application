"""Data access for quiz generation — fetch coverage chunks, persist quiz drafts.

All SQL for the assessment domain lives here; services (quiz.py) call these
methods and never write SQL inline (repository pattern, see CLAUDE.md §6.5).
"""

from __future__ import annotations

import json
import logging
from typing import Any
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.models.question import Question
from asag.rag.retriever import ChunkResult

log = logging.getLogger(__name__)


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
