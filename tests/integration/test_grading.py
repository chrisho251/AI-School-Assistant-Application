"""Integration test for grade_attempt — real Postgres, LLM judge mocked.

Seeds a quiz (1 MCQ + 1 short), one attempt with two answers, runs the grading
orchestrator, and asserts auto_score is written (MCQ deterministic, short via the
mocked judge) and the attempt transitions to ``graded``.

Requires migrations through 0010_answer_audit.sql to be applied.

Run:
    uv run pytest tests/integration/test_grading.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool


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
        self.teacher = uuid.uuid4()
        self.student = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.quiz = uuid.uuid4()
        self.q_mcq = uuid.uuid4()
        self.q_short = uuid.uuid4()
        self.attempt = uuid.uuid4()
        self.a_mcq = uuid.uuid4()
        self.a_short = uuid.uuid4()


async def _seed(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(ids.org), "Grade Org", f"gr-{ids.org.hex[:8]}"),
        )
        for uid, email, role in [
            (ids.teacher, "gr-teacher@test.com", "teacher"),
            (ids.student, "gr-student@test.com", "student"),
        ]:
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s,%s,%s,%s,%s)",
                (str(uid), str(ids.org), email, role, role),
            )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
            (str(ids.class_), str(ids.org), "Gr Class", str(ids.teacher)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
            (str(ids.notebook), str(ids.class_), str(ids.teacher), "Gr Notebook"),
        )
        await conn.execute(
            "INSERT INTO quizzes (id, notebook_id, created_by, title, status) "
            "VALUES (%s,%s,%s,%s,%s)",
            (str(ids.quiz), str(ids.notebook), str(ids.teacher), "Gr Quiz", "published"),
        )
        await conn.execute(
            "INSERT INTO questions (id, quiz_id, ordinal, type, stem, options, answer) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (
                str(ids.q_mcq),
                str(ids.quiz),
                0,
                "mcq",
                "What is 2+2?",
                '[{"key":"A","text":"3"},{"key":"B","text":"4"}]',
                '{"correct_key":"B","explanation":"basic math"}',
            ),
        )
        await conn.execute(
            "INSERT INTO questions (id, quiz_id, ordinal, type, stem, answer, rubric) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (
                str(ids.q_short),
                str(ids.quiz),
                1,
                "short",
                "Explain addition.",
                '{"reference":"Combining two numbers into their sum."}',
                '{"items":[{"criterion":"mentions sum","points":2},'
                '{"criterion":"mentions combine","points":2}],"max_score":4}',
            ),
        )
        await conn.execute(
            "INSERT INTO attempts (id, quiz_id, student_id, status) VALUES (%s,%s,%s,%s)",
            (str(ids.attempt), str(ids.quiz), str(ids.student), "submitted"),
        )
        await conn.execute(
            "INSERT INTO answers (id, attempt_id, question_id, response) VALUES (%s,%s,%s,%s::jsonb)",
            (str(ids.a_mcq), str(ids.attempt), str(ids.q_mcq), '{"selected_key":"B"}'),
        )
        await conn.execute(
            "INSERT INTO answers (id, attempt_id, question_id, response) VALUES (%s,%s,%s,%s::jsonb)",
            (
                str(ids.a_short),
                str(ids.attempt),
                str(ids.q_short),
                '{"text":"Addition combines two numbers into a sum."}',
            ),
        )
        await conn.commit()


async def _cleanup(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute("DELETE FROM quizzes WHERE id = %s", (str(ids.quiz),))
        await conn.execute("DELETE FROM notebooks WHERE id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes WHERE id = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users WHERE org_id = %s", (str(ids.org),))
        await conn.execute("DELETE FROM organizations WHERE id = %s", (str(ids.org),))
        await conn.commit()


@pytest.mark.integration
async def test_integ_grade_attempt_writes_scores(db_url: str) -> None:
    """grade_attempt writes auto_score for both types and marks attempt graded."""
    from asag.assessment.graders.short import _JudgeVerdict
    from asag.assessment.grading import grade_attempt

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        verdict = _JudgeVerdict(
            score=4.0, reasoning="covers sum and combine", matched_rubric_items=["mentions sum"]
        )
        with patch(
            "asag.assessment.graders.short.structured_output",
            new=AsyncMock(return_value=verdict),
        ):
            results = await grade_attempt(ids.attempt, pool=pool)

        assert results[ids.a_mcq].score == 1.0  # deterministic correct
        assert results[ids.a_short].score == 4.0  # mocked judge

        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT id, auto_score FROM answers WHERE attempt_id = %s", (str(ids.attempt),)
            )
            scores = {uuid.UUID(str(r[0])): r[1] for r in await cur.fetchall()}
            cur = await conn.execute(
                "SELECT status FROM attempts WHERE id = %s", (str(ids.attempt),)
            )
            row = await cur.fetchone()

        assert float(scores[ids.a_mcq]) == 1.0
        assert float(scores[ids.a_short]) == 4.0
        assert row is not None and row[0] == "graded"
    finally:
        await _cleanup(db_url, ids)
        await pool.close()
