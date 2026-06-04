"""Integration test for teacher review — override + finalisation, real Postgres.

Seeds an auto-graded attempt (2 answers with auto_score), overrides one answer's
score, finalises the attempt, and asserts final_score = teacher override where set
and auto_score otherwise, finalized_at is stamped, and the attempt is ``finalized``.

Requires migrations through 0010_answer_audit.sql to be applied.

Run:
    uv run pytest tests/integration/test_review.py -v
"""

from __future__ import annotations

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
            "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s)",
            (str(ids.org), "Review Org", f"rv-{ids.org.hex[:8]}"),
        )
        for uid, email, role in [
            (ids.teacher, "rv-teacher@test.com", "teacher"),
            (ids.student, "rv-student@test.com", "student"),
        ]:
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s,%s,%s,%s,%s)",
                (str(uid), str(ids.org), email, role, role),
            )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
            (str(ids.class_), str(ids.org), "Rv Class", str(ids.teacher)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
            (str(ids.notebook), str(ids.class_), str(ids.teacher), "Rv Notebook"),
        )
        await conn.execute(
            "INSERT INTO quizzes (id, notebook_id, created_by, title, status) "
            "VALUES (%s,%s,%s,%s,%s)",
            (str(ids.quiz), str(ids.notebook), str(ids.teacher), "Rv Quiz", "published"),
        )
        for qid, ordinal, qtype in [(ids.q_mcq, 0, "mcq"), (ids.q_short, 1, "short")]:
            await conn.execute(
                "INSERT INTO questions (id, quiz_id, ordinal, type, stem, answer) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                (str(qid), str(ids.quiz), ordinal, qtype, f"Q {ordinal}", "{}"),
            )
        await conn.execute(
            "INSERT INTO attempts (id, quiz_id, student_id, status) VALUES (%s,%s,%s,%s)",
            (str(ids.attempt), str(ids.quiz), str(ids.student), "graded"),
        )
        # MCQ auto 1.0 (will be overridden to 0.5); short auto 3.0 (kept as final)
        for aid, qid, auto in [(ids.a_mcq, ids.q_mcq, 1.0), (ids.a_short, ids.q_short, 3.0)]:
            await conn.execute(
                "INSERT INTO answers (id, attempt_id, question_id, response, auto_score) "
                "VALUES (%s,%s,%s,%s::jsonb,%s)",
                (str(aid), str(ids.attempt), str(qid), "{}", auto),
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
async def test_integ_override_then_finalize(db_url: str) -> None:
    """Override one answer, finalise; final_score honours override + auto fallback."""
    from asag.assessment.review import finalize_attempt, override_answer_score

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        # Teacher overrides the MCQ from auto 1.0 to 0.5 (partial credit decision)
        await override_answer_score(
            ids.a_mcq, ids.teacher, 0.5, pool=pool, feedback="partial credit"
        )

        total = await finalize_attempt(ids.attempt, ids.teacher, pool=pool)
        assert total == 3.5  # 0.5 (override) + 3.0 (auto)

        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT id, teacher_score, final_score, finalized_at, updated_by "
                "FROM answers WHERE attempt_id = %s",
                (str(ids.attempt),),
            )
            rows = {uuid.UUID(str(r[0])): r for r in await cur.fetchall()}
            cur = await conn.execute(
                "SELECT status FROM attempts WHERE id = %s", (str(ids.attempt),)
            )
            status_row = await cur.fetchone()

        mcq_row = rows[ids.a_mcq]
        short_row = rows[ids.a_short]
        assert float(mcq_row[1]) == 0.5  # teacher_score set
        assert float(mcq_row[2]) == 0.5  # final = teacher override
        assert float(short_row[2]) == 3.0  # final = auto (no override)
        assert mcq_row[3] is not None and short_row[3] is not None  # finalized_at stamped
        assert uuid.UUID(str(mcq_row[4])) == ids.teacher  # updated_by audit
        assert status_row is not None and status_row[0] == "finalized"
    finally:
        await _cleanup(db_url, ids)
        await pool.close()
