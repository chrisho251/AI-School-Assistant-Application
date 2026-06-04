"""Integration tests for the review-guard fixes applied after code review.

Fix #2 — ownership checks: a wrong teacher_id is rejected before any mutation.
Fix #3 — ungraded-answer block: finalize raises when an answer still has no score.

Requires migrations through 0010_answer_audit.sql.

Run:
    uv run pytest tests/integration/test_review_guards.py -v
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
        self.other_teacher = uuid.uuid4()
        self.student = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.quiz = uuid.uuid4()
        self.question = uuid.uuid4()
        self.attempt = uuid.uuid4()
        self.answer = uuid.uuid4()


async def _seed(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s)",
            (str(ids.org), "Guard Org", f"gd-{ids.org.hex[:8]}"),
        )
        for uid, email, role in [
            (ids.teacher, "gd-teacher@test.com", "teacher"),
            (ids.other_teacher, "gd-other@test.com", "teacher"),
            (ids.student, "gd-student@test.com", "student"),
        ]:
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s,%s,%s,%s,%s)",
                (str(uid), str(ids.org), email, role, role),
            )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
            (str(ids.class_), str(ids.org), "Gd Class", str(ids.teacher)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
            (str(ids.notebook), str(ids.class_), str(ids.teacher), "Gd Notebook"),
        )
        # Quiz owned by ids.teacher
        await conn.execute(
            "INSERT INTO quizzes (id, notebook_id, created_by, title, status) "
            "VALUES (%s,%s,%s,%s,%s)",
            (str(ids.quiz), str(ids.notebook), str(ids.teacher), "Gd Quiz", "published"),
        )
        await conn.execute(
            "INSERT INTO questions (id, quiz_id, ordinal, type, stem, answer) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
            (str(ids.question), str(ids.quiz), 0, "short", "Q?", "{}"),
        )
        await conn.execute(
            "INSERT INTO attempts (id, quiz_id, student_id, status) VALUES (%s,%s,%s,%s)",
            (str(ids.attempt), str(ids.quiz), str(ids.student), "graded"),
        )
        # Answer with no auto_score — simulates needs_human
        await conn.execute(
            "INSERT INTO answers (id, attempt_id, question_id, response) "
            "VALUES (%s,%s,%s,%s::jsonb)",
            (str(ids.answer), str(ids.attempt), str(ids.question), "{}"),
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
async def test_integ_override_wrong_teacher_raises(db_url: str) -> None:
    """Fix #2: override_answer_score with a non-owner teacher is rejected."""
    from asag.assessment.review import override_answer_score

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)
        with pytest.raises(PermissionError, match="does not own"):
            await override_answer_score(
                ids.answer, ids.other_teacher, 1.0, pool=pool, feedback="nope"
            )
    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_finalize_wrong_teacher_raises(db_url: str) -> None:
    """Fix #2: finalize_attempt with a non-owner teacher is rejected."""
    from asag.assessment.review import finalize_attempt

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)
        with pytest.raises(PermissionError, match="does not own"):
            await finalize_attempt(ids.attempt, ids.other_teacher, pool=pool)
    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_finalize_blocks_when_answer_ungraded(db_url: str) -> None:
    """Fix #3: finalize_attempt raises when an answer has no score at all."""
    from asag.assessment.review import finalize_attempt

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)
        # ids.answer has auto_score=NULL, teacher_score=NULL → ungraded
        with pytest.raises(ValueError, match="no score"):
            await finalize_attempt(ids.attempt, ids.teacher, pool=pool)
    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_finalize_allowed_after_teacher_override(db_url: str) -> None:
    """Fix #3: finalise succeeds once the ungraded answer is overridden."""
    from asag.assessment.review import finalize_attempt, override_answer_score

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)
        await override_answer_score(ids.answer, ids.teacher, 3.0, pool=pool)
        total = await finalize_attempt(ids.attempt, ids.teacher, pool=pool)
        assert total == 3.0
    finally:
        await _cleanup(db_url, ids)
        await pool.close()
