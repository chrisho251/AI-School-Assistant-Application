"""Ingestion pipeline orchestrator.

Entry point: ``ingest_source(source_id, pool=pool, storage=backend)``

Flow:
  1. Load source metadata from DB.
  2. Check idempotency — skip if already "ready".
  3. Mark source as "processing".
  4. Download file bytes from storage.
  5. Write bytes to a temp file (Docling requires a file path).
  6. Parse with the registered loader (route by source_type).
  7. Chunk with the semantic chunker.
  8. Delete any existing chunks for this source (idempotent re-run).
  9. Bulk-insert new chunks.
  10. Update source status to "ready" and commit.

Error handling: any exception sets status to "failed" and commits
before re-raising so the caller can surface it.
"""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.config import get_settings
from asag.core.embeddings import EmbeddingClient
from asag.core.storage import StorageBackend
from asag.ingestion import chunkers as chunker_registry
from asag.ingestion import loaders as loader_registry
from asag.ingestion.repository import ChunkRepository, SourceRepository
from asag.models.ingestion import Chunk, ContentType, IngestResult

log = logging.getLogger(__name__)


async def _embed_chunks(
    chunks: list[Chunk],
    client: EmbeddingClient,
    *,
    batch_size: int = 32,
) -> None:
    """Embed all chunks in batches; mutates chunks in-place."""
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        results = await client.embed_texts([c.content for c in batch])
        for chunk, result in zip(batch, results, strict=True):
            chunk.embedding = result.dense
            chunk.sparse_vector = result.sparse if result.sparse else None


async def ingest_source(
    source_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    storage: StorageBackend,
    chunker_name: str = "semantic",
    embedding_client: EmbeddingClient | None = None,
) -> IngestResult:
    """Run the full ingestion pipeline for one source.

    This function is intentionally idempotent:
      - Re-running with status "ready" is a fast no-op.
      - Re-running with status "failed" retries from scratch.
    """
    async with pool.connection() as conn:
        source_repo = SourceRepository(conn)
        chunk_repo = ChunkRepository(conn)

        # 1. Load metadata
        source = await source_repo.get_by_id(source_id)
        if source is None:
            raise ValueError(f"Source {source_id} not found in DB")

        # 2. Idempotency check
        if source["ingestion_status"] == "ready":
            log.info("Source %s already ingested — skipping", source_id)
            return IngestResult(source_id=source_id, chunks_written=0, status="skipped")

        # 3. Mark processing
        await source_repo.update_status(source_id, "processing")
        await conn.commit()

        try:
            # 4. Download file from storage
            storage_key: str = source["storage_url"]
            file_bytes = await storage.download(storage_key)
            log.info("Downloaded source %s (%d bytes) from storage", source_id, len(file_bytes))

            # 5. Write to temp file (Docling needs a real path; use suffix for MIME hint)
            suffix = Path(source["original_filename"]).suffix or ".pdf"
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / f"source{suffix}"
                tmp_path.write_bytes(file_bytes)

                # 6. Parse (async — Docling via to_thread, ImageLoader via async LLM)
                loader = loader_registry.get(source["source_type"])
                elements = await loader.parse(tmp_path)

            log.info("Loader produced %d elements for source %s", len(elements), source_id)

            # 6b. Enrich image_caption elements with storage URL for UI rendering
            public_url = await storage.get_public_url(storage_key)
            for el in elements:
                if el.content_type == ContentType.image_caption:
                    el.metadata["original_image_url"] = public_url

            # 7. Chunk
            chunker = chunker_registry.get(chunker_name)
            notebook_id = uuid.UUID(str(source["notebook_id"]))
            chunks = chunker.chunk(elements, source_id=source_id, notebook_id=notebook_id)
            log.info("Chunker produced %d chunks for source %s", len(chunks), source_id)

            # 7b. Embed chunks (dense + sparse) in batches of 32
            _client = embedding_client or EmbeddingClient(get_settings().tei_embed_url)
            await _embed_chunks(chunks, _client)
            log.info("Embedded %d chunks for source %s", len(chunks), source_id)

            # 8. Delete old chunks (re-ingestion case)
            deleted = await chunk_repo.delete_by_source(source_id)
            if deleted:
                log.info("Deleted %d stale chunks for source %s", deleted, source_id)

            # 9. Insert new chunks
            written = await chunk_repo.insert_batch(chunks)

            # 10. Mark ready and commit
            await source_repo.update_status(source_id, "ready")
            await conn.commit()

            log.info("Source %s ingested: %d chunks written", source_id, written)
            return IngestResult(source_id=source_id, chunks_written=written, status="ready")

        except Exception as exc:
            log.exception("Ingestion failed for source %s: %s", source_id, exc)
            await source_repo.update_status(source_id, "failed", error_message=str(exc))
            await conn.commit()
            raise
