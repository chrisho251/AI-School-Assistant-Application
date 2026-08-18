"""Seed the Day 12 demo: 1 org, 1 teacher, 3 students, 1 class, 1 notebook.

Idempotent (fixed UUIDs, delete-then-insert). Prints dev bearer tokens + IDs and a
manual smoke checklist. With ``--with-quiz`` it also seeds a *published, proctored*
single-MCQ quiz so the exam-lockdown flow can be demoed end-to-end without running
ingestion (which needs live TEI + Gemini). Real PDFs are uploaded via the UI/API.

Usage:
    PYTHONIOENCODING=utf-8 uv run python scripts/seed_demo.py [--with-quiz]
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import psycopg

from asag.config import get_settings

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop not supported)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEACHER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
STUDENT_IDS = [
    uuid.UUID("33333333-3333-3333-3333-333333333331"),
    uuid.UUID("33333333-3333-3333-3333-333333333332"),
    uuid.UUID("33333333-3333-3333-3333-333333333333"),
]
CLASS_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
NOTEBOOK_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
QUIZ_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
QUESTION_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")


async def _reset(conn: psycopg.AsyncConnection) -> None:
    """Delete prior demo rows (children first) so re-seeding is idempotent."""
    await conn.execute("DELETE FROM attempts WHERE quiz_id = %s", (QUIZ_ID,))  # cascades answers
    await conn.execute("DELETE FROM quizzes WHERE id = %s", (QUIZ_ID,))
    await conn.execute("DELETE FROM notebooks WHERE id = %s", (NOTEBOOK_ID,))  # cascades sources
    await conn.execute("DELETE FROM class_members WHERE class_id = %s", (CLASS_ID,))
    await conn.execute("DELETE FROM classes WHERE id = %s", (CLASS_ID,))
    await conn.execute("DELETE FROM users WHERE id = ANY(%s)", ([TEACHER_ID, *STUDENT_IDS],))
    await conn.execute("DELETE FROM organizations WHERE id = %s", (ORG_ID,))
    await conn.commit()


async def _seed(conn: psycopg.AsyncConnection, *, with_quiz: bool) -> None:
    """Insert the org/users/class/notebook (+ optional proctored quiz)."""
    await conn.execute(
        "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
        (ORG_ID, "Demo School", f"demo-{ORG_ID.hex[:8]}"),
    )
    await conn.execute(
        "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
        (TEACHER_ID, ORG_ID, "teacher@demo.local", "Teacher Demo", "teacher"),
    )
    for i, sid in enumerate(STUDENT_IDS, start=1):
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (sid, ORG_ID, f"student{i}@demo.local", f"Student {i}", "student"),
        )
    await conn.execute(
        "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
        (CLASS_ID, ORG_ID, "Demo Class", TEACHER_ID),
    )
    for sid in STUDENT_IDS:
        await conn.execute(
            "INSERT INTO class_members (class_id, student_id) VALUES (%s, %s)",
            (CLASS_ID, sid),
        )
    # Students reach this notebook (and its quizzes) through class membership in RLS.
    await conn.execute(
        "INSERT INTO notebooks (id, class_id, owner_id, title, subject) VALUES (%s,%s,%s,%s,%s)",
        (NOTEBOOK_ID, CLASS_ID, TEACHER_ID, "Demo Notebook", "General"),
    )

    if with_quiz:
        await conn.execute(
            "INSERT INTO quizzes (id, notebook_id, created_by, title, status, proctoring_config) "
            "VALUES (%s, %s, %s, %s, 'published', %s::jsonb)",
            (
                QUIZ_ID,
                NOTEBOOK_ID,
                TEACHER_ID,
                "Proctored Demo Quiz",
                json.dumps({"enabled": True}),
            ),
        )
        await conn.execute(
            "INSERT INTO questions (id, quiz_id, ordinal, type, stem, options, answer) "
            "VALUES (%s, %s, 0, 'mcq', %s, %s::jsonb, %s::jsonb)",
            (
                QUESTION_ID,
                QUIZ_ID,
                "What does RLS stand for in Postgres?",
                json.dumps(
                    [
                        {"key": "A", "text": "Row Level Security"},
                        {"key": "B", "text": "Remote Login Service"},
                    ]
                ),
                json.dumps({"correct_key": "A"}),
            ),
        )
    await conn.commit()


def _report(*, with_quiz: bool) -> None:
    """Print tokens, IDs, and a manual smoke checklist for the demo walkthrough."""
    teacher_token = f"dev.{TEACHER_ID}.{ORG_ID}.teacher"
    student_tokens = [f"dev.{sid}.{ORG_ID}.student" for sid in STUDENT_IDS]

    print("\n" + "=" * 72)
    print("DEMO DATA SEEDED")
    print("=" * 72)
    print(f"Org ID:       {ORG_ID}")
    print(f"Teacher ID:   {TEACHER_ID}")
    print(f"Class ID:     {CLASS_ID}")
    print(f"Notebook ID:  {NOTEBOOK_ID}")
    for i, sid in enumerate(STUDENT_IDS, start=1):
        print(f"Student {i} ID: {sid}")
    if with_quiz:
        print(f"Quiz ID:      {QUIZ_ID}  (published, proctoring enabled)")

    print("\nReact login — these UUIDs prefill the demo login (frontend/.env VITE_DEMO_*):")
    print(f"  Teacher → user_id {TEACHER_ID}  org_id {ORG_ID}")
    print(f"  Student → user_id {STUDENT_IDS[0]}  org_id {ORG_ID}")

    print("\nDev bearer tokens (curl):")
    print(f'  $T = "Bearer {teacher_token}"')
    print(f'  $S = "Bearer {student_tokens[0]}"')

    print("\nManual smoke checklist (Day 12B):")
    print("  1. Start backend:  uv run uvicorn asag.api.main:app --reload")
    print("  2. Start UI:       cd frontend && pnpm dev  (login prefilled from .env)")
    print("  3. Teacher: log in → open Demo Notebook → upload a PDF → wait 'ready'.")
    print("  4. Teacher: ask a question in chat → verify cited answer.")
    print("  5. Teacher: generate a quiz → publish it.")
    if with_quiz:
        print("  6. Student: log in → Quiz page → 'Proctored Demo Quiz' → Start.")
        print("     → Click 'Enter fullscreen', then switch tab / press F12.")
        print("     → Submit. Teacher Review shows the proctor timeline with those events.")
    else:
        print("  6. Re-run with --with-quiz to also seed a proctored quiz for the lockdown demo.")
    print("=" * 72 + "\n")


async def main() -> None:
    with_quiz = "--with-quiz" in sys.argv
    db_url = get_settings().require_db_url()
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await _reset(conn)
        await _seed(conn, with_quiz=with_quiz)
    _report(with_quiz=with_quiz)


if __name__ == "__main__":
    asyncio.run(main())
