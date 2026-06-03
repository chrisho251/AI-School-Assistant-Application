"""Integration tests for RAG Q&A chain.

Tests use real Postgres (chunks + conversations + messages tables) but mock TEI
and LLM to stay fast and deterministic.

Run:
    uv run pytest tests/integration/test_qa.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.core.embeddings import EmbeddingClient, EmbeddingResult
from asag.core.reranker import RerankClient, RerankResult
from asag.models.qa import AnswerResult
from asag.rag.qa import REFUSAL_PHRASE, answer, stream_answer
from asag.rag.retriever import ChunkResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

DIM = 1024


def _unit_vec(dim: int) -> str:
    vals = [0.0] * DIM
    vals[dim] = 1.0
    return "[" + ",".join(map(str, vals)) + "]"


def _unit_vec_list(dim: int) -> list[float]:
    vals = [0.0] * DIM
    vals[dim] = 1.0
    return vals


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


class _Ids:
    """One isolated test tenant with a notebook, source, and two chunks."""

    def __init__(self) -> None:
        self.org = uuid.uuid4()
        self.user = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.source = uuid.uuid4()
        self.chunk_a = uuid.uuid4()  # "Machine learning" chunk
        self.chunk_b = uuid.uuid4()  # "Neural networks" chunk


async def _seed(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(ids.org), "QA Test Org", f"qa-{ids.org.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (str(ids.user), str(ids.org), "qa@test.com", "QA Tester", "teacher"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (str(ids.class_), str(ids.org), "QA Class", str(ids.user)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
            (str(ids.notebook), str(ids.class_), str(ids.user), "QA Notebook"),
        )
        await conn.execute(
            "INSERT INTO sources (id, notebook_id, source_type, original_filename, "
            "storage_url, ingestion_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(ids.source), str(ids.notebook), "pdf", "qa.pdf", "test/qa.pdf", "ready"),
        )
        # Two chunks with known content
        for chunk_id, ordinal, content in [
            (ids.chunk_a, 0, "Machine learning is a subset of artificial intelligence."),
            (ids.chunk_b, 1, "Neural networks learn by adjusting weights via backpropagation."),
        ]:
            await conn.execute(
                """INSERT INTO chunks
                   (id, source_id, notebook_id, ordinal, content_type, content, metadata,
                    embedding, sparse_vector)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s::jsonb)""",
                (
                    str(chunk_id),
                    str(ids.source),
                    str(ids.notebook),
                    ordinal,
                    "text",
                    content,
                    "{}",
                    _unit_vec(ordinal),
                    "{}",
                ),
            )
        await conn.commit()


async def _cleanup(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        # conversations + messages cascade from notebooks via notebook_id FK
        await conn.execute("DELETE FROM chunks       WHERE source_id  = %s", (str(ids.source),))
        await conn.execute("DELETE FROM sources      WHERE id         = %s", (str(ids.source),))
        # messages reference conversations; conversations reference notebooks
        await conn.execute(
            "DELETE FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE notebook_id = %s)",
            (str(ids.notebook),),
        )
        await conn.execute("DELETE FROM conversations WHERE notebook_id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM notebooks    WHERE id         = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes      WHERE id         = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users        WHERE id         = %s", (str(ids.user),))
        await conn.execute("DELETE FROM organizations WHERE id        = %s", (str(ids.org),))
        await conn.commit()


def _make_known_chunks(ids: _Ids) -> list[ChunkResult]:
    """Two ChunkResult objects mirroring the seeded DB rows."""
    return [
        ChunkResult(
            id=ids.chunk_a,
            source_id=ids.source,
            notebook_id=ids.notebook,
            content="Machine learning is a subset of artificial intelligence.",
            content_type="text",
            page_number=1,
            score=0.9,
        ),
        ChunkResult(
            id=ids.chunk_b,
            source_id=ids.source,
            notebook_id=ids.notebook,
            content="Neural networks learn by adjusting weights via backpropagation.",
            content_type="text",
            page_number=2,
            score=0.7,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests — answer()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_integ_answer_in_domain_with_citations(db_url: str) -> None:
    """answer() returns text with citations and persists conversation + messages."""
    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        known_chunks = _make_known_chunks(ids)

        # Mock retrieve() to return known chunks without hitting TEI
        with (
            patch("asag.rag.qa.retrieve", new=AsyncMock(return_value=known_chunks)),
            patch(
                "asag.rag.qa.chat",
                new=AsyncMock(
                    return_value="Machine learning is a branch of AI [1]. "
                    "It uses neural networks [2]."
                ),
            ),
        ):
            mock_embed = AsyncMock(spec=EmbeddingClient)
            mock_embed.embed_texts.return_value = [
                EmbeddingResult(dense=_unit_vec_list(0), sparse={})
            ]
            mock_reranker = AsyncMock(spec=RerankClient)
            mock_reranker.rerank.return_value = [RerankResult(index=0, score=0.9)]

            result = await answer(
                "What is machine learning?",
                ids.notebook,
                ids.user,
                pool=pool,
                embed_client=mock_embed,
                rerank_client=mock_reranker,
                model="gemini/gemini-2.5-flash",
            )

        assert isinstance(result, AnswerResult)
        assert "[1]" in result.answer or "[2]" in result.answer
        assert len(result.citations) == 2
        assert result.citations[0].chunk_id == ids.chunk_a
        assert result.citations[1].chunk_id == ids.chunk_b

        # Verify DB persistence
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT id FROM conversations WHERE id = %s", (str(result.conversation_id),)
            )
            assert await cur.fetchone() is not None, "Conversation row must be created"

            cur = await conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY created_at",
                (str(result.conversation_id),),
            )
            rows = await cur.fetchall()

        assert len(rows) == 2
        assert rows[0][0] == "user"
        assert rows[0][1] == "What is machine learning?"
        assert rows[1][0] == "assistant"
        assert "[1]" in rows[1][1]

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_answer_out_of_domain_returns_refusal(db_url: str) -> None:
    """answer() returns refusal phrase when LLM determines context is insufficient."""
    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        known_chunks = _make_known_chunks(ids)

        with (
            patch("asag.rag.qa.retrieve", new=AsyncMock(return_value=known_chunks)),
            patch("asag.rag.qa.chat", new=AsyncMock(return_value=REFUSAL_PHRASE)),
        ):
            mock_embed = AsyncMock(spec=EmbeddingClient)
            mock_embed.embed_texts.return_value = [
                EmbeddingResult(dense=_unit_vec_list(0), sparse={})
            ]
            mock_reranker = AsyncMock(spec=RerankClient)
            mock_reranker.rerank.return_value = []

            result = await answer(
                "What is the history of ancient Rome?",
                ids.notebook,
                ids.user,
                pool=pool,
                embed_client=mock_embed,
                rerank_client=mock_reranker,
                model="gemini/gemini-2.5-flash",
            )

        assert result.answer == REFUSAL_PHRASE
        assert result.citations == []

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_answer_continues_existing_conversation(db_url: str) -> None:
    """answer() with an existing conversation_id reuses it instead of creating new."""
    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        # Create a conversation first
        existing_conv_id = uuid.uuid4()
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            await conn.execute(
                "INSERT INTO conversations (id, notebook_id, user_id) VALUES (%s, %s, %s)",
                (str(existing_conv_id), str(ids.notebook), str(ids.user)),
            )
            await conn.commit()

        known_chunks = _make_known_chunks(ids)

        with (
            patch("asag.rag.qa.retrieve", new=AsyncMock(return_value=known_chunks)),
            patch("asag.rag.qa.chat", new=AsyncMock(return_value="Answer [1].")),
        ):
            mock_embed = AsyncMock(spec=EmbeddingClient)
            mock_embed.embed_texts.return_value = [
                EmbeddingResult(dense=_unit_vec_list(0), sparse={})
            ]
            mock_reranker = AsyncMock(spec=RerankClient)
            mock_reranker.rerank.return_value = [RerankResult(index=0, score=0.9)]

            result = await answer(
                "Follow-up question",
                ids.notebook,
                ids.user,
                pool=pool,
                embed_client=mock_embed,
                rerank_client=mock_reranker,
                model="gemini/gemini-2.5-flash",
                conversation_id=existing_conv_id,
            )

        assert result.conversation_id == existing_conv_id

        # Should only be 1 conversation in total
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM conversations WHERE notebook_id = %s",
                (str(ids.notebook),),
            )
            row = await cur.fetchone()

        assert row is not None and row[0] == 1

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


# ---------------------------------------------------------------------------
# Tests — stream_answer()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_integ_stream_answer_yields_tokens_and_persists(db_url: str) -> None:
    """stream_answer() yields tokens and saves to DB after exhaustion."""
    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        known_chunks = _make_known_chunks(ids)
        token_sequence = ["ML ", "is ", "AI [1]."]

        async def _fake_astream(*args, **kwargs):  # noqa: ANN202
            for t in token_sequence:
                yield t

        with (
            patch("asag.rag.qa.retrieve", new=AsyncMock(return_value=known_chunks)),
            patch("asag.rag.qa.astream_chat", new=_fake_astream),
        ):
            mock_embed = AsyncMock(spec=EmbeddingClient)
            mock_embed.embed_texts.return_value = [
                EmbeddingResult(dense=_unit_vec_list(0), sparse={})
            ]
            mock_reranker = AsyncMock(spec=RerankClient)
            mock_reranker.rerank.return_value = [RerankResult(index=0, score=0.9)]

            collected: list[str] = []
            async for token in stream_answer(
                "What is ML?",
                ids.notebook,
                ids.user,
                pool=pool,
                embed_client=mock_embed,
                rerank_client=mock_reranker,
                model="gemini/gemini-2.5-flash",
            ):
                collected.append(token)

        assert collected == token_sequence
        full = "".join(collected)
        assert "[1]" in full

        # DB must have been written after streaming completed
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM messages WHERE conversation_id IN "
                "(SELECT id FROM conversations WHERE notebook_id = %s)",
                (str(ids.notebook),),
            )
            row = await cur.fetchone()

        # 2 messages: user + assistant
        assert row is not None and row[0] == 2

    finally:
        await _cleanup(db_url, ids)
        await pool.close()
