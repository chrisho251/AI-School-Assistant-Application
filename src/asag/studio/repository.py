"""Data access for the studio domain — coverage chunks + artifact persistence.

All SQL for slide generation lives here; services (outline.py, slides.py) call
these methods and never write SQL inline (repository pattern, CLAUDE.md §6.5).
"""

from __future__ import annotations

import json
import logging
from typing import Any
import uuid

from psycopg_pool import AsyncConnectionPool

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


class StudioRepository:
    """Postgres access for the studio domain (outlines + slide-deck artifacts).

    Args:
        pool: Async connection pool. RLS context (if any) is set by the caller;
              POC slide generation runs as a server-side task.
    """

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def fetch_notebook_chunks(
        self, notebook_id: uuid.UUID, *, limit: int = 30
    ) -> list[ChunkResult]:
        """Return up to *limit* chunks for a notebook, ordered for broad coverage.

        Ordering by (source_id, ordinal) keeps each source's chunks contiguous so a
        truncated set still spans whole sections rather than random fragments.
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

    async def create_artifact(self, notebook_id: uuid.UUID, *, kind: str, title: str) -> uuid.UUID:
        """Insert an artifact row in ``generating`` status; return its id."""
        artifact_id = uuid.uuid4()
        await self._execute(
            "INSERT INTO artifacts (id, notebook_id, kind, title, status) "
            "VALUES (%s, %s, %s, %s, 'generating')",
            (str(artifact_id), str(notebook_id), kind, title),
        )
        return artifact_id

    async def mark_ready(
        self, artifact_id: uuid.UUID, *, file_url: str, payload: dict[str, Any]
    ) -> None:
        """Transition an artifact to ``ready`` with its file URL and outline payload."""
        await self._execute(
            "UPDATE artifacts SET status = 'ready', file_url = %s, payload = %s::jsonb, "
            "updated_at = now() WHERE id = %s",
            (file_url, json.dumps(payload), str(artifact_id)),
        )

    async def mark_failed(self, artifact_id: uuid.UUID, *, error_message: str) -> None:
        """Transition an artifact to ``failed`` with an error message."""
        await self._execute(
            "UPDATE artifacts SET status = 'failed', error_message = %s, updated_at = now() "
            "WHERE id = %s",
            (error_message[:2000], str(artifact_id)),
        )

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        """Run a single autocommit statement on a pooled connection."""
        async with self.pool.connection() as conn:
            await conn.execute(sql, params)
