"""Integration test — proctor event lifecycle through the API on Postgres.

A student records lockdown events on their in-progress attempt; the teacher reads
the timeline. Also asserts the security boundaries: events are refused once the
attempt is submitted, and a different student cannot write to the attempt.
"""

from __future__ import annotations

import json
import uuid

from httpx import AsyncClient
import psycopg
import pytest

from tests.integration.conftest import auth_header

pytestmark = pytest.mark.integration


async def test_integ_api_proctor_events(api: AsyncClient, db_url: str) -> None:
    org = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    klass, notebook, quiz, question = (uuid.uuid4() for _ in range(4))

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
                "INSERT INTO class_members (class_id, student_id) VALUES (%s,%s)", (klass, student)
            )
            await c.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
                (notebook, klass, teacher, "NB"),
            )
            await c.execute(
                "INSERT INTO quizzes (id, notebook_id, created_by, title, status, proctoring_config)"
                " VALUES (%s,%s,%s,%s,'published',%s::jsonb)",
                (quiz, notebook, teacher, "Quiz", json.dumps({"enabled": True})),
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
            await c.execute("DELETE FROM attempts WHERE quiz_id = %s", (quiz,))
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

        resp = await api.post("/attempts/start", json={"quiz_id": str(quiz)}, headers=s_hdr)
        assert resp.status_code == 201, resp.text
        attempt_id = resp.json()["id"]

        # Student records two lockdown violations.
        for ev in ("tab_hidden", "fullscreen_exit"):
            r = await api.post(
                f"/attempts/{attempt_id}/proctor_event",
                json={"event_type": ev, "payload": {}},
                headers=s_hdr,
            )
            assert r.status_code == 204, r.text

        # A different student cannot write to this attempt (RLS → 403).
        other = auth_header(uuid.uuid4(), org, "student")
        r = await api.post(
            f"/attempts/{attempt_id}/proctor_event",
            json={"event_type": "tab_hidden"},
            headers=other,
        )
        assert r.status_code in (403, 404)

        # Teacher reads the timeline in order.
        r = await api.get(f"/attempts/{attempt_id}/proctor_events", headers=t_hdr)
        assert r.status_code == 200, r.text
        events = r.json()
        assert [e["type"] for e in events] == ["tab_hidden", "fullscreen_exit"]
        assert all("at" in e for e in events)

        # After submit the proctor log is closed (409).
        resp = await api.post(
            f"/attempts/{attempt_id}/submit",
            json={"answers": [{"question_id": str(question), "response": {"selected_key": "B"}}]},
            headers=s_hdr,
        )
        assert resp.status_code == 200, resp.text
        r = await api.post(
            f"/attempts/{attempt_id}/proctor_event",
            json={"event_type": "tab_hidden"},
            headers=s_hdr,
        )
        assert r.status_code == 409, r.text
    finally:
        await cleanup()
