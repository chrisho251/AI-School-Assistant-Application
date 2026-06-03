"""Hybrid retrieval: dense + sparse search, RRF fusion, bge-reranker-v2-m3 reranking.

Entry points:
  hybrid_search(query, notebook_id, ...) — dense + sparse fused via RRF
  retrieve(query, notebook_id, ...)      — hybrid → rerank → top k_final
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
from typing import Any
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.core.embeddings import EmbeddingClient
from asag.core.reranker import RerankClient

log = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """One retrieved chunk with its relevance score.

    Produced by dense_search, sparse_search, hybrid_search, and retrieve.
    The ``score`` field is:
      - cosine similarity (dense_search)
      - sparse dot product (sparse_search)
      - RRF score (hybrid_search)
      - reranker score (retrieve)
    """

    id: uuid.UUID
    source_id: uuid.UUID
    notebook_id: uuid.UUID
    content: str
    content_type: str
    page_number: int | None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _vec_literal(embedding: list[float]) -> str:
    """Convert float list to pgvector literal '[f1,f2,...]'."""
    return "[" + ",".join(map(str, embedding)) + "]"


def _row_to_chunk(d: dict[str, Any]) -> ChunkResult:
    """Build a ChunkResult from a psycopg3 row dict."""
    return ChunkResult(
        id=uuid.UUID(str(d["id"])),
        source_id=uuid.UUID(str(d["source_id"])),
        notebook_id=uuid.UUID(str(d["notebook_id"])),
        content=str(d["content"]),
        content_type=str(d["content_type"]),
        page_number=int(d["page_number"]) if d["page_number"] is not None else None,
        metadata=d["metadata"] if isinstance(d["metadata"], dict) else {},
        score=float(d["score"]),
    )


# ---------------------------------------------------------------------------
# Search primitives
# ---------------------------------------------------------------------------


async def dense_search(
    query_embedding: list[float],
    notebook_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    k: int = 30,
) -> list[ChunkResult]:
    """Return top-k chunks by cosine similarity to query_embedding.

    Args:
        query_embedding: Dense query vector (1024-d for BGE-M3).
        notebook_id: Security filter — only chunks from this notebook.
        pool: Connection pool.
        k: Number of results.

    Returns:
        ChunkResult list sorted by cosine similarity descending.
    """
    vec = _vec_literal(query_embedding)

    # ORDER BY the <=> operator directly so the HNSW index is used for the scan.
    # The score expression 1 - distance is computed after the index scan.
    sql = """
        SELECT id, source_id, notebook_id, content, content_type, page_number, metadata,
               (1.0 - (embedding <=> %s::vector)) AS score
        FROM chunks
        WHERE notebook_id = %s
          AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s
    """

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (vec, str(notebook_id), vec, k))
        cols = [d.name for d in cur.description]  # type: ignore[union-attr]
        rows = await cur.fetchall()

    return [_row_to_chunk(dict(zip(cols, row, strict=False))) for row in rows]


async def sparse_search(
    query_sparse: dict[str, float],
    notebook_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    k: int = 30,
) -> list[ChunkResult]:
    """Return top-k chunks by sparse dot product score.

    Uses the GIN index on ``sparse_vector`` for a pre-filter (?|), then
    computes the exact dot product via ``jsonb_each_text`` for the smaller
    candidate set.

    Args:
        query_sparse: Sparse query vector as token_id (str) → weight (float).
        notebook_id: Security filter — only chunks from this notebook.
        pool: Connection pool.
        k: Number of results.

    Returns:
        ChunkResult list sorted by dot product score descending.
        Empty if query_sparse has no keys (no terms → no signal).
    """
    if not query_sparse:
        return []

    query_keys = list(query_sparse.keys())
    query_json = json.dumps(query_sparse)

    # ?| pre-filters via GIN; correlated subquery computes exact dot product.
    sql = """
        SELECT c.id, c.source_id, c.notebook_id, c.content, c.content_type,
               c.page_number, c.metadata,
               COALESCE((
                   SELECT SUM((c.sparse_vector ->> kv.key)::float * kv.val::float)
                   FROM jsonb_each_text(%s::jsonb) AS kv(key, val)
                   WHERE c.sparse_vector ? kv.key
               ), 0.0) AS score
        FROM chunks c
        WHERE c.notebook_id = %s
          AND c.sparse_vector IS NOT NULL
          AND c.sparse_vector ?| %s::text[]
        ORDER BY score DESC
        LIMIT %s
    """

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (query_json, str(notebook_id), query_keys, k))
        cols = [d.name for d in cur.description]  # type: ignore[union-attr]
        rows = await cur.fetchall()

    return [_row_to_chunk(dict(zip(cols, row, strict=False))) for row in rows]


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    *ranked_lists: list[ChunkResult],
    k: int = 60,
) -> list[ChunkResult]:
    """Fuse multiple ranked lists via Reciprocal Rank Fusion (RRF).

    Args:
        *ranked_lists: Any number of ChunkResult lists, each sorted by relevance.
        k: RRF constant (default 60, from the original Cormack et al. paper).

    Returns:
        Merged list sorted by fused RRF score descending.
        ``chunk.score`` is overwritten with the RRF score.
    """
    scores: dict[uuid.UUID, float] = {}
    chunks: dict[uuid.UUID, ChunkResult] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, 1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunks[chunk.id] = chunk

    merged = sorted(chunks.values(), key=lambda c: scores[c.id], reverse=True)
    for chunk in merged:
        chunk.score = scores[chunk.id]
    return merged


# ---------------------------------------------------------------------------
# High-level pipelines
# ---------------------------------------------------------------------------


async def hybrid_search(
    query: str,
    notebook_id: uuid.UUID,
    *,
    embed_client: EmbeddingClient,
    pool: AsyncConnectionPool,
    k: int = 20,
    search_k: int = 30,
) -> list[ChunkResult]:
    """Dense + sparse search fused via RRF.

    Args:
        query: Natural language query string.
        notebook_id: Notebook scope filter (enforced in SQL).
        embed_client: BGE-M3 embedding client.
        pool: DB connection pool.
        k: Number of results after fusion.
        search_k: Candidates fetched per individual search before fusion.

    Returns:
        Up to k ChunkResult items sorted by RRF score descending.
    """
    embed_results = await embed_client.embed_texts([query])
    embedding = embed_results[0].dense
    sparse = embed_results[0].sparse

    dense_res, sparse_res = await asyncio.gather(
        dense_search(embedding, notebook_id, pool=pool, k=search_k),
        sparse_search(sparse, notebook_id, pool=pool, k=search_k),
    )

    fused = reciprocal_rank_fusion(dense_res, sparse_res)
    log.debug(
        "Hybrid: dense=%d sparse=%d fused=%d returning top %d",
        len(dense_res),
        len(sparse_res),
        len(fused),
        k,
    )
    return fused[:k]


async def retrieve(
    query: str,
    notebook_id: uuid.UUID,
    *,
    embed_client: EmbeddingClient,
    rerank_client: RerankClient,
    pool: AsyncConnectionPool,
    k_final: int = 5,
    search_k: int = 30,
) -> list[ChunkResult]:
    """Full retrieval pipeline: hybrid search → rerank → top k_final.

    Args:
        query: Natural language query string.
        notebook_id: Notebook scope filter.
        embed_client: BGE-M3 embedding client.
        rerank_client: bge-reranker-v2-m3 client.
        pool: DB connection pool.
        k_final: Number of results returned after reranking.
        search_k: Candidates per individual search before fusion.

    Returns:
        Top k_final ChunkResult items ordered by reranker score descending.
        ``chunk.score`` is the reranker relevance score.
    """
    # Fetch 4× candidates to give the reranker more signal
    candidates = await hybrid_search(
        query,
        notebook_id,
        embed_client=embed_client,
        pool=pool,
        k=k_final * 4,
        search_k=search_k,
    )

    if not candidates:
        return []

    rerank_results = await rerank_client.rerank(
        query,
        [c.content for c in candidates],
        top_n=k_final,
    )

    # Guard against a desync between candidates and reranker indices: a malformed
    # response with an out-of-range index would otherwise raise an opaque IndexError.
    reranked: list[ChunkResult] = []
    for r in rerank_results:
        if not 0 <= r.index < len(candidates):
            log.warning("Reranker returned out-of-range index %d; skipping", r.index)
            continue
        chunk = candidates[r.index]
        chunk.score = r.score
        reranked.append(chunk)

    log.debug("Retrieve: %d candidates → %d reranked", len(candidates), len(reranked))
    return reranked
