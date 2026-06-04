"""Integration test — notebook CRUD + RLS isolation through the FastAPI app.

Needs only Postgres (no TEI/LLM/storage). Exercises the real auth → RLS → repository
path: dev tokens authenticate, ``get_db`` pins the ``asag_app`` role, and the DB
policies decide visibility. Seeding/cleanup use the postgres superuser (bypasses RLS).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
import psycopg
import pytest

from tests.integration.conftest import auth_header

pytestmark = pytest.mark.integration


async def test_integ_api_notebook_crud_and_rls(api: AsyncClient, db_url: str) -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    teacher_a, teacher_b = uuid.uuid4(), uuid.uuid4()
    class_a = uuid.uuid4()

    async def seed() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s),(%s,%s,%s)",
                (org_a, "A", f"a-{org_a.hex[:8]}", org_b, "B", f"b-{org_b.hex[:8]}"),
            )
            await c.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES "
                "(%s,%s,%s,%s,'teacher'),(%s,%s,%s,%s,'teacher')",
                (
                    teacher_a,
                    org_a,
                    f"{teacher_a}@x.com",
                    "TA",
                    teacher_b,
                    org_b,
                    f"{teacher_b}@x.com",
                    "TB",
                ),
            )
            await c.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
                (class_a, org_a, "Class A", teacher_a),
            )
            await c.commit()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute("DELETE FROM notebooks WHERE class_id = %s", (class_a,))
            await c.execute("DELETE FROM classes WHERE id = %s", (class_a,))
            await c.execute("DELETE FROM users WHERE id = ANY(%s)", ([teacher_a, teacher_b],))
            await c.execute("DELETE FROM organizations WHERE id = ANY(%s)", ([org_a, org_b],))
            await c.commit()

    await seed()
    try:
        ta_hdr = auth_header(teacher_a, org_a, "teacher")
        tb_hdr = auth_header(teacher_b, org_b, "teacher")

        # Teacher A creates a notebook.
        resp = await api.post(
            "/notebooks",
            json={"class_id": str(class_a), "title": "Bio 101"},
            headers=ta_hdr,
        )
        assert resp.status_code == 201, resp.text
        nb_id = resp.json()["id"]

        # Teacher A sees it.
        resp = await api.get("/notebooks", headers=ta_hdr)
        assert any(n["id"] == nb_id for n in resp.json())

        # Teacher A can fetch it directly.
        assert (await api.get(f"/notebooks/{nb_id}", headers=ta_hdr)).status_code == 200

        # Teacher B (other org) must NOT see it — RLS isolation.
        resp = await api.get("/notebooks", headers=tb_hdr)
        assert all(n["id"] != nb_id for n in resp.json())
        assert (await api.get(f"/notebooks/{nb_id}", headers=tb_hdr)).status_code == 404
    finally:
        await cleanup()
