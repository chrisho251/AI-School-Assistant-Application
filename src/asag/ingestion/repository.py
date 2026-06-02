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


class SourceRepository:
    """Read/write access to the `sources` table."""

    def __init__(self, db: AsyncConnection) -> None:
        self.db: AsyncConnection = db

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
        """Bulk-insert chunks. Returns number of rows inserted."""
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
            )
            for c in chunks
        ]

        async with self.db.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO chunks
                    (id, source_id, notebook_id, ordinal, page_number,
                     content_type, content, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id, ordinal) DO UPDATE
                    SET content  = EXCLUDED.content,
                        metadata = EXCLUDED.metadata
                """,
                rows,
            )
        log.debug("Inserted %d chunks for source %s", len(chunks), chunks[0].source_id)
        return len(chunks)
