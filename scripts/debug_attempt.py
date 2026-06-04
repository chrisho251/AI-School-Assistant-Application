"""Debug — print an attempt's status and per-answer scores (auto/teacher/final).

Usage:
    uv run python scripts/debug_attempt.py <attempt_id>
"""

from __future__ import annotations

import asyncio
import json
import sys

import psycopg

from asag.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(attempt_id: str) -> None:
    db_url = get_settings().require_db_url()
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        cur = await conn.execute(
            "SELECT status, submitted_at FROM attempts WHERE id = %s", (attempt_id,)
        )
        att = await cur.fetchone()
        if att is None:
            print(f"Attempt {attempt_id} not found")
            return
        print(f"Attempt {attempt_id}\n  status={att[0]}  submitted_at={att[1]}")

        cur = await conn.execute(
            "SELECT a.id, q.type, q.ordinal, a.response, a.auto_score, a.auto_feedback, "
            "a.teacher_score, a.final_score "
            "FROM answers a JOIN questions q ON q.id = a.question_id "
            "WHERE a.attempt_id = %s ORDER BY q.ordinal",
            (attempt_id,),
        )
        rows = await cur.fetchall()

    print(f"\n  {len(rows)} answer(s):")
    for r in rows:
        ans_id, qtype, ordinal, response, auto, auto_fb, teacher, final = r
        print(f"\n  Q{ordinal} [{qtype}] answer={ans_id}")
        print(f"    response: {json.dumps(response, ensure_ascii=False)}")
        print(f"    auto_score={auto}  teacher_score={teacher}  final_score={final}")
        if auto_fb:
            print(f"    auto_feedback: {auto_fb[:200]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: debug_attempt.py <attempt_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
