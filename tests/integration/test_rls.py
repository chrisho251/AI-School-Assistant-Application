"""Integration test for RLS — multi-tenant isolation.

Pattern:
  - Data setup:  postgres superuser (bypasses RLS) — so we can INSERT freely.
  - RLS tests:   SET ROLE asag_app (non-superuser, subject to RLS).
  - Cleanup:     fresh postgres connection (superuser, bypasses RLS).
"""

from __future__ import annotations

import uuid

import psycopg
from psycopg import AsyncConnection
import pytest

from asag.config import ConfigError, get_settings


@pytest.fixture(scope="session")
async def db_url() -> str:
    """Get Supabase DB URL from config, skip test if not available."""
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
async def db_conn(db_url: str) -> AsyncConnection:
    """Async connection to test database."""
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        yield conn


async def _as_app_user(
    conn: AsyncConnection,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Switch connection to asag_app role with RLS context.

    PostgreSQL SET does not accept $1 parameters — UUIDs are hex-safe literals.
    Must call _reset_role() after RLS testing is done.
    """
    await conn.execute("SET ROLE asag_app")
    await conn.execute(f"SET app.current_user_id TO '{user_id}'")
    await conn.execute(f"SET app.current_org_id TO '{org_id}'")


async def _reset_role(conn: AsyncConnection) -> None:
    """Restore postgres superuser role (disables RLS enforcement)."""
    await conn.execute("RESET ROLE")


@pytest.mark.integration
async def test_integ_rls_org_isolation(db_conn: AsyncConnection, db_url: str) -> None:
    """User in Org A cannot see notebooks from Org B (RLS enforcement).

    Setup:
      - 2 organizations (org_a, org_b)
      - 2 users (user_a1 in org_a, user_b1 in org_b)
      - 1 class + 1 notebook in org_a

    Assert:
      - user_a1 (asag_app role) sees the notebook
      - user_b1 (asag_app role) gets no rows — RLS filters it out
    """
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()
    user_a1_id = uuid.uuid4()
    user_b1_id = uuid.uuid4()
    class_a_id = uuid.uuid4()
    notebook_id = uuid.uuid4()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute("DELETE FROM notebooks WHERE id = %s", (notebook_id,))
            await c.execute("DELETE FROM classes WHERE id = %s", (class_a_id,))
            await c.execute("DELETE FROM users WHERE id = ANY(%s)", ([user_a1_id, user_b1_id],))
            await c.execute("DELETE FROM organizations WHERE id = ANY(%s)", ([org_a_id, org_b_id],))
            await c.commit()

    try:
        # ---- Setup as postgres superuser (RLS bypassed) ----
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (org_a_id, "Org A", f"org-a-{org_a_id.hex[:8]}"),
            )
            await cur.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (org_b_id, "Org B", f"org-b-{org_b_id.hex[:8]}"),
            )
            await cur.execute(
                "INSERT INTO users (id, org_id, email, full_name, role)"
                " VALUES (%s, %s, %s, %s, %s)",
                (user_a1_id, org_a_id, "user_a1@example.com", "User A1", "teacher"),
            )
            await cur.execute(
                "INSERT INTO users (id, org_id, email, full_name, role)"
                " VALUES (%s, %s, %s, %s, %s)",
                (user_b1_id, org_b_id, "user_b1@example.com", "User B1", "student"),
            )
            await cur.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
                (class_a_id, org_a_id, "Class A", user_a1_id),
            )
            await cur.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
                (notebook_id, class_a_id, user_a1_id, "Test Notebook"),
            )
        await db_conn.commit()

        # ---- Test 1: user_a1 in org_a should see the notebook ----
        await _as_app_user(db_conn, user_a1_id, org_a_id)
        async with db_conn.cursor() as cur:
            await cur.execute("SELECT id, title FROM notebooks WHERE id = %s", (notebook_id,))
            result = await cur.fetchone()
        await _reset_role(db_conn)

        assert result is not None, "user_a1 should see notebook in their org"
        assert result[0] == notebook_id
        assert result[1] == "Test Notebook"

        # ---- Test 2: user_b1 in org_b must NOT see the notebook ----
        await _as_app_user(db_conn, user_b1_id, org_b_id)
        async with db_conn.cursor() as cur:
            await cur.execute("SELECT id, title FROM notebooks WHERE id = %s", (notebook_id,))
            result = await cur.fetchone()
        await _reset_role(db_conn)

        assert result is None, "user_b1 must NOT see notebook from org_a (RLS isolation)"

    finally:
        await cleanup()


@pytest.mark.integration
async def test_integ_rls_class_member_access(db_conn: AsyncConnection, db_url: str) -> None:
    """Student in a class can read the class's notebooks via RLS.

    Setup:
      - 1 org, 1 teacher, 1 student
      - student is a class_member of the teacher's class
      - 1 notebook in that class

    Assert:
      - student (asag_app role) can read the notebook via class membership
    """
    org_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    student_id = uuid.uuid4()
    class_id = uuid.uuid4()
    notebook_id = uuid.uuid4()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute("DELETE FROM notebooks WHERE id = %s", (notebook_id,))
            await c.execute("DELETE FROM class_members WHERE class_id = %s", (class_id,))
            await c.execute("DELETE FROM classes WHERE id = %s", (class_id,))
            await c.execute("DELETE FROM users WHERE id = ANY(%s)", ([teacher_id, student_id],))
            await c.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
            await c.commit()

    try:
        # ---- Setup as postgres superuser (RLS bypassed) ----
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (org_id, "Test Org", f"test-org-{org_id.hex[:8]}"),
            )
            await cur.execute(
                "INSERT INTO users (id, org_id, email, full_name, role)"
                " VALUES (%s, %s, %s, %s, %s)",
                (teacher_id, org_id, "teacher@example.com", "Teacher", "teacher"),
            )
            await cur.execute(
                "INSERT INTO users (id, org_id, email, full_name, role)"
                " VALUES (%s, %s, %s, %s, %s)",
                (student_id, org_id, "student@example.com", "Student", "student"),
            )
            await cur.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
                (class_id, org_id, "Test Class", teacher_id),
            )
            await cur.execute(
                "INSERT INTO class_members (class_id, student_id) VALUES (%s, %s)",
                (class_id, student_id),
            )
            await cur.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
                (notebook_id, class_id, teacher_id, "Class Notebook"),
            )
        await db_conn.commit()

        # ---- Test: student sees notebook via class_members policy ----
        await _as_app_user(db_conn, student_id, org_id)
        async with db_conn.cursor() as cur:
            await cur.execute("SELECT id, title FROM notebooks WHERE id = %s", (notebook_id,))
            result = await cur.fetchone()
        await _reset_role(db_conn)

        assert result is not None, "student should see notebook via class membership"
        assert result[0] == notebook_id

    finally:
        await cleanup()
