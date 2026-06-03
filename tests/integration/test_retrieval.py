"""Integration tests for hybrid retrieval + reranker.

Tests use pre-seeded chunks with known embeddings to verify correctness
without requiring TEI to be running. The DB must be reachable.

Run:
    uv run pytest tests/integration/test_retrieval.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
import uuid

import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.core.embeddings import EmbeddingClient, EmbeddingResult
from asag.core.reranker import RerankClient, RerankResult
from asag.rag.retriever import (
    dense_search,
    hybrid_search,
    retrieve,
    sparse_search,
)

# ---------------------------------------------------------------------------
# Helpers — vector literals
# ---------------------------------------------------------------------------

DIM = 1024


def _unit_vec(dim: int) -> str:
    """pgvector literal with 1.0 at position *dim*, 0.0 elsewhere."""
    vals = [0.0] * DIM
    vals[dim] = 1.0
    return "[" + ",".join(map(str, vals)) + "]"


def _neg_unit_vec(dim: int) -> str:
    vals = [0.0] * DIM
    vals[dim] = -1.0
    return "[" + ",".join(map(str, vals)) + "]"


def _unit_vec_list(dim: int) -> list[float]:
    vals = [0.0] * DIM
    vals[dim] = 1.0
    return vals


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


class _TestIds:
    """UUIDs for one isolated test tenant."""

    def __init__(self) -> None:
        self.org = uuid.uuid4()
        self.user = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.source = uuid.uuid4()
        # Three chunks with known geometry
        self.chunk_relevant = uuid.uuid4()  # dim-0 unit vec, tokens 100+200
        self.chunk_medium = uuid.uuid4()  # dim-1 unit vec, token 100 only
        self.chunk_irrelevant = uuid.uuid4()  # dim-0 negative vec, token 300 only


async def _seed(db_url: str, ids: _TestIds) -> None:
    """Insert test tenant + 3 chunks with known embeddings and sparse vectors."""
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(ids.org), "Retrieval Test Org", f"ret-{ids.org.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (str(ids.user), str(ids.org), "ret@test.com", "Retrieval Tester", "teacher"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (str(ids.class_), str(ids.org), "Ret Class", str(ids.user)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
            (str(ids.notebook), str(ids.class_), str(ids.user), "Ret Notebook"),
        )
        await conn.execute(
            "INSERT INTO sources (id, notebook_id, source_type, original_filename, "
            "storage_url, ingestion_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                str(ids.source),
                str(ids.notebook),
                "pdf",
                "test.pdf",
                "test/test.pdf",
                "ready",
            ),
        )

        # Chunk 0 — relevant: aligns with query dim-0 and shares tokens 100+200
        await conn.execute(
            """INSERT INTO chunks
               (id, source_id, notebook_id, ordinal, content_type, content, metadata,
                embedding, sparse_vector)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s::jsonb)""",
            (
                str(ids.chunk_relevant),
                str(ids.source),
                str(ids.notebook),
                0,
                "text",
                "Machine learning is a subset of artificial intelligence.",
                "{}",
                _unit_vec(0),
                json.dumps({"100": 0.8, "200": 0.6}),
            ),
        )

        # Chunk 1 — medium: orthogonal to query, partial token overlap
        await conn.execute(
            """INSERT INTO chunks
               (id, source_id, notebook_id, ordinal, content_type, content, metadata,
                embedding, sparse_vector)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s::jsonb)""",
            (
                str(ids.chunk_medium),
                str(ids.source),
                str(ids.notebook),
                1,
                "text",
                "Deep learning uses neural networks with many layers.",
                "{}",
                _unit_vec(1),
                json.dumps({"100": 0.3}),
            ),
        )

        # Chunk 2 — irrelevant: opposite direction, no token overlap with query
        await conn.execute(
            """INSERT INTO chunks
               (id, source_id, notebook_id, ordinal, content_type, content, metadata,
                embedding, sparse_vector)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s::jsonb)""",
            (
                str(ids.chunk_irrelevant),
                str(ids.source),
                str(ids.notebook),
                2,
                "text",
                "The history of ancient Rome spans centuries.",
                "{}",
                _neg_unit_vec(0),
                json.dumps({"300": 0.9}),
            ),
        )

        await conn.commit()


async def _cleanup(db_url: str, ids: _TestIds) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute("DELETE FROM chunks       WHERE source_id  = %s", (str(ids.source),))
        await conn.execute("DELETE FROM sources      WHERE id         = %s", (str(ids.source),))
        await conn.execute("DELETE FROM notebooks    WHERE id         = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes      WHERE id         = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users        WHERE id         = %s", (str(ids.user),))
        await conn.execute("DELETE FROM organizations WHERE id        = %s", (str(ids.org),))
        await conn.commit()


# ---------------------------------------------------------------------------
# Tests — Session 4A: dense + sparse + RRF
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_integ_dense_search_correct_order(db_url: str) -> None:
    """Relevant chunk (cosine sim=1) ranks above orthogonal (0) and opposite (-1)."""
    ids = _TestIds()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        # Query vector aligns with chunk_relevant (dim-0 unit vec)
        results = await dense_search(
            _unit_vec_list(0),
            ids.notebook,
            pool=pool,
            k=10,
        )

        assert len(results) >= 3
        top_ids = [r.id for r in results]
        assert top_ids[0] == ids.chunk_relevant, "Relevant chunk must be top-1"
        # chunk_medium (orthogonal, score≈0) ranked before chunk_irrelevant (score≈-1)
        assert top_ids.index(ids.chunk_medium) < top_ids.index(ids.chunk_irrelevant)
        # Scores must be in descending order
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_dense_search_notebook_filter(db_url: str) -> None:
    """dense_search never returns chunks from a different notebook."""
    ids = _TestIds()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        # Query against a random (nonexistent) notebook_id
        results = await dense_search(
            _unit_vec_list(0),
            uuid.uuid4(),  # different notebook — no chunks
            pool=pool,
            k=10,
        )

        assert results == []

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_sparse_search_correct_order(db_url: str) -> None:
    """Chunk with highest dot product is ranked first; no-overlap chunk excluded."""
    ids = _TestIds()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        # Query sparse: tokens 100 (w=1.0) + 200 (w=0.5)
        # chunk_relevant dot product: 100→0.8*1.0 + 200→0.6*0.5 = 1.1
        # chunk_medium dot product:   100→0.3*1.0                = 0.3
        # chunk_irrelevant: no overlap → not returned
        query_sparse = {"100": 1.0, "200": 0.5}
        results = await sparse_search(query_sparse, ids.notebook, pool=pool, k=10)

        assert len(results) >= 1
        assert results[0].id == ids.chunk_relevant
        result_ids = {r.id for r in results}
        assert ids.chunk_irrelevant not in result_ids, "No-overlap chunk must be excluded"
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_sparse_search_empty_query(db_url: str) -> None:
    """Empty query sparse returns empty list without hitting DB."""
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        results = await sparse_search({}, uuid.uuid4(), pool=pool)
        assert results == []
    finally:
        await pool.close()


@pytest.mark.integration
async def test_integ_hybrid_search_top_chunk(db_url: str) -> None:
    """hybrid_search returns relevant chunk at top-1 with mocked embed_client."""
    ids = _TestIds()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        mock_embed = AsyncMock(spec=EmbeddingClient)
        mock_embed.embed_texts.return_value = [
            EmbeddingResult(
                dense=_unit_vec_list(0),
                sparse={"100": 1.0, "200": 0.5},
            )
        ]

        results = await hybrid_search(
            "machine learning overview",
            ids.notebook,
            embed_client=mock_embed,
            pool=pool,
            k=10,
        )

        assert len(results) >= 1
        assert results[0].id == ids.chunk_relevant, "Relevant chunk must be top-1 after RRF"

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


# ---------------------------------------------------------------------------
# Tests — Session 4B: reranker integration
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_integ_retrieve_respects_reranker_order(db_url: str) -> None:
    """retrieve() returns chunks in the order the reranker specifies."""
    ids = _TestIds()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        mock_embed = AsyncMock(spec=EmbeddingClient)
        mock_embed.embed_texts.return_value = [
            EmbeddingResult(
                dense=_unit_vec_list(0),
                sparse={"100": 1.0, "200": 0.5},
            )
        ]

        # Mock reranker inverts typical order: chunk_irrelevant first
        mock_reranker = AsyncMock(spec=RerankClient)

        async def _fake_rerank(query: str, texts: list[str], *, top_n: int | None = None):
            # Return scores that place the last candidate first
            n = len(texts)
            return [
                RerankResult(index=i, score=float(n - i))
                for i in range(n if top_n is None else min(top_n, n))
            ]

        mock_reranker.rerank.side_effect = _fake_rerank

        results = await retrieve(
            "machine learning overview",
            ids.notebook,
            embed_client=mock_embed,
            rerank_client=mock_reranker,
            pool=pool,
            k_final=3,
        )

        assert len(results) <= 3
        # Scores must be the reranker's scores (descending)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_retrieve_returns_empty_for_empty_notebook(db_url: str) -> None:
    """retrieve() returns empty list when no chunks exist for notebook."""
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        mock_embed = AsyncMock(spec=EmbeddingClient)
        mock_embed.embed_texts.return_value = [
            EmbeddingResult(dense=_unit_vec_list(0), sparse={"100": 1.0})
        ]
        mock_reranker = AsyncMock(spec=RerankClient)
        mock_reranker.rerank.return_value = []

        results = await retrieve(
            "any query",
            uuid.uuid4(),  # nonexistent notebook
            embed_client=mock_embed,
            rerank_client=mock_reranker,
            pool=pool,
            k_final=5,
        )

        assert results == []

    finally:
        await pool.close()
