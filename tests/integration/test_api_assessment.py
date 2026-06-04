"""Integration test — attempt lifecycle through the API, end to end on Postgres.

Covers start → submit → (background MCQ grading) → get → teacher finalize. Uses a
single deterministic MCQ so no LLM/TEI is needed: the whole flow runs against
Postgres alone. The background grading task is awaited within the ASGI cycle, so
by the time the submit response returns the attempt is already ``graded``.
"""

from __future__ import annotations

import json
import uuid

from httpx import AsyncClient
import psycopg
import pytest

from tests.integration.conftest import auth_header

pytestmark = pytest.mark.integration


async def test_integ_api_attempt_lifecycle(api: AsyncClient, db_url: str) -> None:
    org = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    klass = uuid.uuid4()
    notebook = uuid.uuid4()
    quiz = uuid.uuid4()
    question = uuid.uuid4()

    async def seed() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s)",
                (org, "Org", f"org-{org.hex[:8]}"),
            )
            await c.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES "
                "(%s,%s,%s,%s,'teacher'),(%s,%s,%s,%s,'student')",
                (teacher, org, f"{teacher}@x.com", "T", student, org, f"{student}@x.com", "S"),
            )
            await c.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
                (klass, org, "C", teacher),
            )
            await c.execute(
                "INSERT INTO class_members (class_id, student_id) VALUES (%s,%s)",
                (klass, student),
            )
            await c.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
                (notebook, klass, teacher, "NB"),
            )
            await c.execute(
                "INSERT INTO quizzes (id, notebook_id, created_by, title, status) "
                "VALUES (%s,%s,%s,%s,'published')",
                (quiz, notebook, teacher, "Quiz"),
            )
            await c.execute(
                "INSERT INTO questions (id, quiz_id, ordinal, type, stem, options, answer) "
                "VALUES (%s,%s,0,'mcq',%s,%s::jsonb,%s::jsonb)",
                (
                    question,
                    quiz,
                    "2+2=?",
                    json.dumps([{"key": "A", "text": "3"}, {"key": "B", "text": "4"}]),
                    json.dumps({"correct_key": "B"}),
                ),
            )
            await c.commit()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute("DELETE FROM attempts WHERE quiz_id = %s", (quiz,))  # cascades answers
            await c.execute("DELETE FROM questions WHERE quiz_id = %s", (quiz,))
            await c.execute("DELETE FROM quizzes WHERE id = %s", (quiz,))
            await c.execute("DELETE FROM notebooks WHERE id = %s", (notebook,))
            await c.execute("DELETE FROM class_members WHERE class_id = %s", (klass,))
            await c.execute("DELETE FROM classes WHERE id = %s", (klass,))
            await c.execute("DELETE FROM users WHERE id = ANY(%s)", ([teacher, student],))
            await c.execute("DELETE FROM organizations WHERE id = %s", (org,))
            await c.commit()

    await seed()
    try:
        s_hdr = auth_header(student, org, "student")
        t_hdr = auth_header(teacher, org, "teacher")

        # Student fetches the quiz — answer key must NOT be present.
        resp = await api.get(f"/quizzes/{quiz}", headers=s_hdr)
        assert resp.status_code == 200, resp.text
        q0 = resp.json()["questions"][0]
        assert "answer" not in q0 and "rubric" not in q0

        # Start an attempt.
        resp = await api.post("/attempts/start", json={"quiz_id": str(quiz)}, headers=s_hdr)
        assert resp.status_code == 201, resp.text
        attempt_id = resp.json()["id"]

        # Submit the correct option; background grading runs in-cycle.
        resp = await api.post(
            f"/attempts/{attempt_id}/submit",
            json={"answers": [{"question_id": str(question), "response": {"selected_key": "B"}}]},
            headers=s_hdr,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "submitted"

        # After grading the attempt is 'graded'.
        resp = await api.get(f"/attempts/{attempt_id}", headers=s_hdr)
        assert resp.json()["status"] == "graded"

        # A different student cannot read this attempt (RLS).
        other = auth_header(uuid.uuid4(), org, "student")
        assert (await api.get(f"/attempts/{attempt_id}", headers=other)).status_code == 404

        # Teacher finalizes — correct MCQ scores 1.0.
        resp = await api.post(f"/attempts/{attempt_id}/finalize", headers=t_hdr)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_score"] == pytest.approx(1.0)
    finally:
        await cleanup()
