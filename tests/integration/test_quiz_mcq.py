"""Integration tests for MCQ generation.

Uses real Postgres (notebook + chunks seeded) but mocks the LLM structured_output
call so the test is deterministic. Verifies schema + grounding: each generated
question's source_chunk_ids resolve to the actual seeded chunks.

Run:
    uv run pytest tests/integration/test_quiz_mcq.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

import psycopg
import pytest

from asag.assessment.generators.mcq import _MCQBatch, _MCQItem, generate_mcq
from asag.config import ConfigError, get_settings
from asag.models.question import MCQOption, QuestionType
from asag.rag.retriever import ChunkResult


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


class _Ids:
    def __init__(self) -> None:
        self.org = uuid.uuid4()
        self.user = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.source = uuid.uuid4()
        self.chunk_a = uuid.uuid4()
        self.chunk_b = uuid.uuid4()


async def _seed(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(ids.org), "Quiz Org", f"quiz-{ids.org.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (str(ids.user), str(ids.org), "quiz@test.com", "Quiz Teacher", "teacher"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (str(ids.class_), str(ids.org), "Quiz Class", str(ids.user)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
            (str(ids.notebook), str(ids.class_), str(ids.user), "Quiz Notebook"),
        )
        await conn.execute(
            "INSERT INTO sources (id, notebook_id, source_type, original_filename, "
            "storage_url, ingestion_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(ids.source), str(ids.notebook), "pdf", "quiz.pdf", "test/quiz.pdf", "ready"),
        )
        for chunk_id, ordinal, content in [
            (ids.chunk_a, 0, "Photosynthesis converts light energy into chemical energy."),
            (ids.chunk_b, 1, "Chlorophyll absorbs light most strongly in the blue and red bands."),
        ]:
            await conn.execute(
                "INSERT INTO chunks (id, source_id, notebook_id, ordinal, content_type, content, "
                "metadata) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (str(chunk_id), str(ids.source), str(ids.notebook), ordinal, "text", content, "{}"),
            )
        await conn.commit()


async def _cleanup(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute("DELETE FROM chunks WHERE source_id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM sources WHERE id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM notebooks WHERE id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes WHERE id = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users WHERE id = %s", (str(ids.user),))
        await conn.execute("DELETE FROM organizations WHERE id = %s", (str(ids.org),))
        await conn.commit()


def _fake_batch() -> _MCQBatch:
    """Two well-formed MCQ items citing source refs [1] and [2]."""
    return _MCQBatch(
        questions=[
            _MCQItem(
                stem="What does photosynthesis produce?",
                options=[
                    MCQOption(key="A", text="Chemical energy"),
                    MCQOption(key="B", text="Sound energy"),
                    MCQOption(key="C", text="Nuclear energy"),
                    MCQOption(key="D", text="Magnetic energy"),
                ],
                correct_key="A",
                explanation="Source 1 states it converts light into chemical energy.",
                source_refs=[1],
            ),
            _MCQItem(
                stem="Which light bands does chlorophyll absorb most strongly?",
                options=[
                    MCQOption(key="A", text="Green and yellow"),
                    MCQOption(key="B", text="Blue and red"),
                    MCQOption(key="C", text="Only ultraviolet"),
                    MCQOption(key="D", text="Only infrared"),
                ],
                correct_key="B",
                explanation="Source 2 says blue and red bands.",
                source_refs=[2],
            ),
        ]
    )


def _known_chunks(ids: _Ids) -> list[ChunkResult]:
    return [
        ChunkResult(
            id=ids.chunk_a,
            source_id=ids.source,
            notebook_id=ids.notebook,
            content="Photosynthesis converts light energy into chemical energy.",
            content_type="text",
            page_number=None,
        ),
        ChunkResult(
            id=ids.chunk_b,
            source_id=ids.source,
            notebook_id=ids.notebook,
            content="Chlorophyll absorbs light most strongly in the blue and red bands.",
            content_type="text",
            page_number=None,
        ),
    ]


@pytest.mark.integration
async def test_integ_generate_mcq_grounded(db_url: str) -> None:
    """generate_mcq returns schema-valid, grounded MCQ resolving to seeded chunks."""
    ids = _Ids()
    try:
        await _seed(db_url, ids)
        chunks = _known_chunks(ids)

        with patch(
            "asag.assessment.generators.mcq.structured_output",
            new=AsyncMock(return_value=_fake_batch()),
        ):
            questions = await generate_mcq(chunks, 2, model="gemini/gemini-2.5-flash")

        assert len(questions) == 2
        valid_chunk_ids = {ids.chunk_a, ids.chunk_b}
        for q in questions:
            assert q.type is QuestionType.mcq
            assert q.options is not None and len(q.options) == 4
            assert not q.needs_review
            # grounding: every cited chunk id is a real seeded chunk
            assert q.source_chunk_ids
            assert set(q.source_chunk_ids) <= valid_chunk_ids
            # unique distractors
            texts = [o.text for o in q.options]
            assert len(set(texts)) == len(texts)
            # correct answer is one of the options
            assert q.answer["correct_key"] in {o.key for o in q.options}
    finally:
        await _cleanup(db_url, ids)


@pytest.mark.integration
async def test_integ_generate_mcq_empty_chunks_returns_empty(db_url: str) -> None:
    """No chunks → no LLM call, empty result."""
    questions = await generate_mcq([], 5, model="gemini/gemini-2.5-flash")
    assert questions == []
