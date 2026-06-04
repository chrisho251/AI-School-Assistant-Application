"""Integration test — teacher review endpoints (list attempts, answers, override).

Builds on the attempt lifecycle: a student submits a wrong MCQ (auto_score 0), then
the teacher lists the attempt, reads its answers, overrides the score, and finalises.
Runs on Postgres alone (deterministic MCQ — no LLM/TEI).
"""

from __future__ import annotations

import json
import uuid

from httpx import AsyncClient
import psycopg
import pytest

from tests.integration.conftest import auth_header

pytestmark = pytest.mark.integration


async def test_integ_api_teacher_review(api: AsyncClient, db_url: str) -> None:
    org = uuid.uuid4()
    teacher, student, other_teacher = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
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
                "(%s,%s,%s,%s,'teacher'),(%s,%s,%s,%s,'student'),(%s,%s,%s,%s,'teacher')",
                (
                    teacher,
                    org,
                    f"{teacher}@x.com",
                    "T",
                    student,
                    org,
                    f"{student}@x.com",
                    "S",
                    other_teacher,
                    org,
                    f"{other_teacher}@x.com",
                    "T2",
                ),
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
            await c.execute("DELETE FROM attempts WHERE quiz_id = %s", (quiz,))
            await c.execute("DELETE FROM questions WHERE quiz_id = %s", (quiz,))
            await c.execute("DELETE FROM quizzes WHERE id = %s", (quiz,))
            await c.execute("DELETE FROM notebooks WHERE id = %s", (notebook,))
            await c.execute("DELETE FROM class_members WHERE class_id = %s", (klass,))
            await c.execute("DELETE FROM classes WHERE id = %s", (klass,))
            await c.execute(
                "DELETE FROM users WHERE id = ANY(%s)", ([teacher, student, other_teacher],)
            )
            await c.execute("DELETE FROM organizations WHERE id = %s", (org,))
            await c.commit()

    await seed()
    try:
        s_hdr = auth_header(student, org, "student")
        t_hdr = auth_header(teacher, org, "teacher")

        # Student starts + submits the WRONG option → auto_score 0 after grading.
        attempt_id = (
            await api.post("/attempts/start", json={"quiz_id": str(quiz)}, headers=s_hdr)
        ).json()["id"]
        resp = await api.post(
            f"/attempts/{attempt_id}/submit",
            json={"answers": [{"question_id": str(question), "response": {"selected_key": "A"}}]},
            headers=s_hdr,
        )
        assert resp.status_code == 200, resp.text

        # Teacher lists attempts on their quiz.
        resp = await api.get(f"/attempts/quiz/{quiz}", headers=t_hdr)
        assert resp.status_code == 200, resp.text
        assert any(a["id"] == attempt_id for a in resp.json())

        # A different teacher (not the creator) sees no attempts (RLS).
        other = auth_header(other_teacher, org, "teacher")
        assert (await api.get(f"/attempts/quiz/{quiz}", headers=other)).json() == []

        # Students must not read provisional scores (teacher-only endpoint).
        assert (await api.get(f"/attempts/{attempt_id}/answers", headers=s_hdr)).status_code == 403

        # Teacher reads the answers with score columns.
        resp = await api.get(f"/attempts/{attempt_id}/answers", headers=t_hdr)
        assert resp.status_code == 200, resp.text
        answers = resp.json()
        assert len(answers) == 1
        assert answers[0]["auto_score"] == pytest.approx(0.0)
        answer_id = answers[0]["answer_id"]

        # Teacher overrides the score to full marks.
        resp = await api.patch(
            f"/attempts/{attempt_id}/answers/{answer_id}/score",
            json={"score": 1.0, "feedback": "Counted on appeal"},
            headers=t_hdr,
        )
        assert resp.status_code == 200, resp.text

        # A student cannot override (teacher-only route).
        resp = await api.patch(
            f"/attempts/{attempt_id}/answers/{answer_id}/score",
            json={"score": 1.0},
            headers=s_hdr,
        )
        assert resp.status_code == 403

        # Finalise reflects the override.
        resp = await api.post(f"/attempts/{attempt_id}/finalize", headers=t_hdr)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_score"] == pytest.approx(1.0)
    finally:
        await cleanup()
