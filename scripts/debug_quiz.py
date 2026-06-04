"""Debug — print a quiz's full questions incl. answer key, rubric, grounding.

Shows what the API deliberately hides from students (answer/rubric) plus the
source_chunk_ids and needs_review flags, so you can verify grounding.

Usage:
    uv run python scripts/debug_quiz.py <quiz_id>
"""

from __future__ import annotations

import asyncio
import json
import sys

import psycopg

from asag.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(quiz_id: str) -> None:
    db_url = get_settings().require_db_url()
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        cur = await conn.execute(
            "SELECT id, ordinal, type, stem, options, answer, rubric, "
            "source_chunk_ids, needs_review FROM questions WHERE quiz_id = %s ORDER BY ordinal",
            (quiz_id,),
        )
        rows = await cur.fetchall()

    if not rows:
        print(f"No questions for quiz {quiz_id}")
        return

    for r in rows:
        qid, ordinal, qtype, stem, options, answer, rubric, chunk_ids, needs_review = r
        print(f"\n{'=' * 70}")
        print(f"Q{ordinal} [{qtype}]  id={qid}  needs_review={needs_review}")
        print(f"  stem: {stem}")
        if options:
            for o in options:
                print(f"    ({o['key']}) {o['text']}")
        print(f"  answer: {json.dumps(answer, ensure_ascii=False)}")
        if rubric:
            print(f"  rubric: {json.dumps(rubric, ensure_ascii=False)}")
        print(f"  source_chunk_ids: {len(chunk_ids or [])} chunk(s) -> {chunk_ids}")
    print(f"\n{'=' * 70}\n{len(rows)} questions total")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: debug_quiz.py <quiz_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
