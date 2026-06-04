"""Integration test for the full quiz orchestrator.

Real Postgres (chunks seeded + quiz/questions persisted); LLM generators and the
grounding validator are mocked. Verifies a draft quiz is saved with both MCQ and
short questions, and that an ungrounded question is flagged needs_review.

Requires migration 0009_question_review.sql to be applied.

Run:
    uv run pytest tests/integration/test_quiz_full.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

import psycopg
import pytest

from asag.assessment.generators.mcq import _MCQBatch, _MCQItem
from asag.assessment.generators.short import _ShortBatch, _ShortItem
from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.models.question import MCQOption, QuestionType, QuizConfig, RubricItem


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
            (str(ids.org), "Full Quiz Org", f"fq-{ids.org.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (str(ids.user), str(ids.org), "fq@test.com", "FQ Teacher", "teacher"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (str(ids.class_), str(ids.org), "FQ Class", str(ids.user)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
            (str(ids.notebook), str(ids.class_), str(ids.user), "FQ Notebook"),
        )
        await conn.execute(
            "INSERT INTO sources (id, notebook_id, source_type, original_filename, "
            "storage_url, ingestion_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(ids.source), str(ids.notebook), "pdf", "fq.pdf", "test/fq.pdf", "ready"),
        )
        for chunk_id, ordinal, content in [
            (ids.chunk_a, 0, "The mitochondrion is the powerhouse of the cell."),
            (ids.chunk_b, 1, "ATP is the primary energy currency of the cell."),
        ]:
            await conn.execute(
                "INSERT INTO chunks (id, source_id, notebook_id, ordinal, content_type, content, "
                "metadata) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (str(chunk_id), str(ids.source), str(ids.notebook), ordinal, "text", content, "{}"),
            )
        await conn.commit()


async def _cleanup(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        # questions cascade from quizzes; quizzes cascade from notebook
        await conn.execute("DELETE FROM quizzes WHERE notebook_id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM chunks WHERE source_id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM sources WHERE id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM notebooks WHERE id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes WHERE id = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users WHERE id = %s", (str(ids.user),))
        await conn.execute("DELETE FROM organizations WHERE id = %s", (str(ids.org),))
        await conn.commit()


def _mcq_batch() -> _MCQBatch:
    """Two MCQs: the second cites an out-of-range ref → flagged needs_review."""
    opts = [
        MCQOption(key="A", text="ATP"),
        MCQOption(key="B", text="DNA"),
        MCQOption(key="C", text="RNA"),
        MCQOption(key="D", text="Lipid"),
    ]
    return _MCQBatch(
        questions=[
            _MCQItem(
                stem="What is the cell's energy currency?",
                options=opts,
                correct_key="A",
                explanation="Source 2: ATP is the primary energy currency.",
                source_refs=[2],
            ),
            _MCQItem(
                stem="An ungrounded question.",
                options=opts,
                correct_key="A",
                explanation="No supporting source.",
                source_refs=[99],
            ),
        ]
    )


def _short_batch() -> _ShortBatch:
    return _ShortBatch(
        questions=[
            _ShortItem(
                stem="Describe the role of the mitochondrion.",
                reference_answer="It is the powerhouse of the cell, producing energy.",
                rubric_items=[
                    RubricItem(criterion="mentions powerhouse", points=2),
                    RubricItem(criterion="mentions energy", points=2),
                ],
                source_refs=[1],
            )
        ]
    )


@pytest.mark.integration
async def test_integ_generate_quiz_saves_draft_with_review_flags(db_url: str) -> None:
    """generate_quiz persists a draft quiz; ungrounded question is flagged."""
    from asag.assessment.quiz import generate_quiz

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        config = QuizConfig(
            title="Cell Biology Quiz",
            mix={QuestionType.mcq: 2, QuestionType.short: 1},
        )

        with (
            patch(
                "asag.assessment.generators.mcq.structured_output",
                new=AsyncMock(return_value=_mcq_batch()),
            ),
            patch(
                "asag.assessment.generators.short.structured_output",
                new=AsyncMock(return_value=_short_batch()),
            ),
            patch(
                "asag.assessment.quiz.validate_grounding",
                new=AsyncMock(return_value=True),
            ),
        ):
            quiz = await generate_quiz(
                ids.notebook,
                config,
                created_by=ids.user,
                pool=pool,
            )

        assert quiz.status == "draft"
        assert len(quiz.questions) == 3  # 2 mcq + 1 short
        assert sum(1 for q in quiz.questions if q.needs_review) >= 1

        # Verify DB persistence
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute("SELECT status FROM quizzes WHERE id = %s", (str(quiz.id),))
            row = await cur.fetchone()
            assert row is not None and row[0] == "draft"

            cur = await conn.execute(
                "SELECT type, needs_review FROM questions WHERE quiz_id = %s ORDER BY ordinal",
                (str(quiz.id),),
            )
            rows = await cur.fetchall()

        assert len(rows) == 3
        types = [r[0] for r in rows]
        assert types.count("mcq") == 2
        assert types.count("short") == 1
        assert any(r[1] for r in rows), "at least one question persisted needs_review=True"
    finally:
        await _cleanup(db_url, ids)
        await pool.close()
