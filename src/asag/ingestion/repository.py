"""DB repository classes for the ingestion domain.

All SQL for sources and chunks lives here — pipeline and API
route handlers never write raw queries directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any
import uuid

from psycopg import AsyncConnection

from asag.models.ingestion import Chunk

log = logging.getLogger(__name__)


class NotebookRepository:
    """Read/write access to the `notebooks` table (RLS-scoped connection)."""

    def __init__(self, db: AsyncConnection) -> None:
        self.db: AsyncConnection = db

    async def get_class_teacher(self, class_id: uuid.UUID) -> uuid.UUID | None:
        """Return the class's ``teacher_id`` if the class is visible to the caller.

        RLS filters classes to the caller's org, so a None result means the class
        is missing or belongs to another tenant.
        """
        async with self.db.cursor() as cur:
            await cur.execute("SELECT teacher_id FROM classes WHERE id = %s", (str(class_id),))
            row = await cur.fetchone()
        return uuid.UUID(str(row[0])) if row else None

    async def create(
        self,
        *,
        class_id: uuid.UUID,
        owner_id: uuid.UUID,
        title: str,
        subject: str | None,
        description: str | None,
    ) -> dict[str, Any]:
        """Insert a notebook and return the created row.

        The RLS insert policy requires ``owner_id = current_user_id()``, so a caller
        cannot create notebooks on another user's behalf.
        """
        async with self.db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO notebooks (class_id, owner_id, title, subject, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, class_id, owner_id, title, subject, description
                """,
                (str(class_id), str(owner_id), title, subject, description),
            )
            row = await cur.fetchone()
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
        return dict(zip(cols, row, strict=False))  # type: ignore[arg-type]

    async def list_for_user(self) -> list[dict[str, Any]]:
        """Return every notebook visible to the current user (RLS does the filtering)."""
        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT id, class_id, owner_id, title, subject, description "
                "FROM notebooks ORDER BY created_at DESC"
            )
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
            rows = await cur.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def get_by_id(self, notebook_id: uuid.UUID) -> dict[str, Any] | None:
        """Return one visible notebook, or None if missing/not permitted (RLS)."""
        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT id, class_id, owner_id, title, subject, description "
                "FROM notebooks WHERE id = %s",
                (str(notebook_id),),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
        return dict(zip(cols, row, strict=False))


class SourceRepository:
    """Read/write access to the `sources` table."""

    def __init__(self, db: AsyncConnection) -> None:
        self.db: AsyncConnection = db

    async def create(
        self,
        *,
        notebook_id: uuid.UUID,
        source_type: str,
        original_filename: str,
        storage_url: str,
        checksum: str,
        file_size_bytes: int | None = None,
    ) -> dict[str, Any]:
        """Insert a source row (status defaults to ``pending``) and return it.

        The RLS insert policy requires the notebook be owned by the current user.
        """
        async with self.db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO sources
                    (notebook_id, source_type, original_filename, storage_url,
                     checksum, file_size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, notebook_id, source_type, original_filename,
                          storage_url, ingestion_status
                """,
                (
                    str(notebook_id),
                    source_type,
                    original_filename,
                    storage_url,
                    checksum,
                    file_size_bytes,
                ),
            )
            row = await cur.fetchone()
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
        return dict(zip(cols, row, strict=False))  # type: ignore[arg-type]

    async def list_by_notebook(self, notebook_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all sources for a notebook visible to the caller (RLS-filtered)."""
        async with self.db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, notebook_id, source_type, original_filename,
                       storage_url, ingestion_status
                FROM sources WHERE notebook_id = %s ORDER BY created_at DESC
                """,
                (str(notebook_id),),
            )
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
            rows = await cur.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def get_by_id(self, source_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, notebook_id, source_type, original_filename,
                       storage_url, checksum, ingestion_status
                FROM sources WHERE id = %s
                """,
                (str(source_id),),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]  # type: ignore[union-attr]
            return dict(zip(cols, row, strict=False))

    async def update_status(
        self,
        source_id: uuid.UUID,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        async with self.db.cursor() as cur:
            await cur.execute(
                """
                UPDATE sources
                SET ingestion_status = %s, error_message = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (status, error_message, str(source_id)),
            )


class ChunkRepository:
    """Write access to the `chunks` table."""

    def __init__(self, db: AsyncConnection) -> None:
        self.db: AsyncConnection = db

    async def delete_by_source(self, source_id: uuid.UUID) -> int:
        """Remove all chunks for *source_id* to allow clean re-ingestion."""
        async with self.db.cursor() as cur:
            await cur.execute(
                "DELETE FROM chunks WHERE source_id = %s",
                (str(source_id),),
            )
            return cur.rowcount or 0

    async def insert_batch(self, chunks: list[Chunk]) -> int:
        """Bulk-insert chunks including embedding and sparse_vector if populated."""
        if not chunks:
            return 0

        rows = [
            (
                str(c.id),
                str(c.source_id),
                str(c.notebook_id),
                c.ordinal,
                c.page_number,
                c.content_type.value,
                c.content,
                json.dumps(c.metadata),
                # pgvector literal string "[f1,f2,...]"; NULL if not yet embedded
                ("[" + ",".join(map(str, c.embedding)) + "]") if c.embedding is not None else None,
                json.dumps(c.sparse_vector) if c.sparse_vector is not None else None,
            )
            for c in chunks
        ]

        async with self.db.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO chunks
                    (id, source_id, notebook_id, ordinal, page_number,
                     content_type, content, metadata, embedding, sparse_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s::jsonb)
                ON CONFLICT (source_id, ordinal) DO UPDATE
                    SET content       = EXCLUDED.content,
                        metadata      = EXCLUDED.metadata,
                        embedding     = EXCLUDED.embedding,
                        sparse_vector = EXCLUDED.sparse_vector
                """,
                rows,
            )
        log.debug("Inserted %d chunks for source %s", len(chunks), chunks[0].source_id)
        return len(chunks)
