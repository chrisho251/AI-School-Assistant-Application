"""Seed minimal demo: 1 org, 1 teacher, 1 student, 1 class.

For manual testing Day 9 API. Prints the IDs and dev tokens.

Usage:
    PYTHONIOENCODING=utf-8 uv run python scripts/seed_demo_min.py

Then use the printed tokens in curl/browser tests.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import psycopg

from asag.config import get_settings

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop not supported)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main() -> None:
    cfg = get_settings()
    db_url = cfg.require_db_url()

    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    teacher_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    student_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    class_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        # Cleanup (idempotent — delete existing demo data)
        await conn.execute("DELETE FROM class_members WHERE class_id = %s", (class_id,))
        await conn.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        await conn.execute("DELETE FROM users WHERE id = ANY(%s)", ([teacher_id, student_id],))
        await conn.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
        await conn.commit()

        # Seed
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (org_id, "Demo", f"demo-{org_id.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (teacher_id, org_id, "teacher@demo.local", "Teacher Demo", "teacher"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (student_id, org_id, "student@demo.local", "Student Demo", "student"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (class_id, org_id, "Demo Class", teacher_id),
        )
        await conn.execute(
            "INSERT INTO class_members (class_id, student_id) VALUES (%s, %s)",
            (class_id, student_id),
        )
        await conn.commit()

    teacher_token = f"dev.{teacher_id}.{org_id}.teacher"
    student_token = f"dev.{student_id}.{org_id}.student"
    class_id_str = str(class_id)

    print("\n" + "=" * 70)
    print("DEMO DATA SEEDED")
    print("=" * 70)
    print(f"\nOrganization ID: {org_id}")
    print(f"Teacher ID:      {teacher_id}")
    print(f"Student ID:      {student_id}")
    print(f"Class ID:        {class_id}")
    print("\n📌 COPY-PASTE THESE COMMANDS FOR curl TESTING:\n")
    print(f'$T = "Bearer {teacher_token}"')
    print(f'$S = "Bearer {student_token}"')
    print(f'$C = "{class_id_str}"')
    print("\n📝 Example test (create notebook):")
    print(
        """
curl.exe -X POST http://localhost:8000/notebooks \\
  -H "Authorization: $T" \\
  -H "Content-Type: application/json" \\
  -d '{"class_id":"'$C'","title":"Biology 101"}'
"""
    )
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
