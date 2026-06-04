"""Debug helper — inspect sources + chunks for a notebook (superuser, bypasses RLS).

Usage:
    $env:PYTHONIOENCODING="utf-8"; uv run python scripts/debug_sources.py <notebook_id>
"""

from __future__ import annotations

import asyncio
import sys

import psycopg

from asag.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(notebook_id: str) -> None:
    db_url = get_settings().require_db_url()
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        # Sources (superuser — sees everything regardless of RLS)
        cur = await conn.execute(
            "SELECT id, notebook_id, ingestion_status, error_message, created_at "
            "FROM sources WHERE notebook_id = %s ORDER BY created_at DESC",
            (notebook_id,),
        )
        rows = await cur.fetchall()
        print(f"\n=== SOURCES for notebook {notebook_id} (superuser view) ===")
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  id={r[0]} status={r[2]} error={r[3]!r} created={r[4]}")

        # Chunks count per source
        cur = await conn.execute(
            "SELECT source_id, COUNT(*), COUNT(embedding) "
            "FROM chunks WHERE notebook_id = %s GROUP BY source_id",
            (notebook_id,),
        )
        crows = await cur.fetchall()
        print("\n=== CHUNKS ===")
        if not crows:
            print("  (none)")
        for r in crows:
            print(f"  source={r[0]} chunks={r[1]} with_embedding={r[2]}")

        # Notebook ownership sanity
        cur = await conn.execute(
            "SELECT id, owner_id, class_id FROM notebooks WHERE id = %s", (notebook_id,)
        )
        nb = await cur.fetchone()
        print("\n=== NOTEBOOK ===")
        print(f"  {nb}")


if __name__ == "__main__":
    nb = sys.argv[1] if len(sys.argv) > 1 else "5e7c4b1a-55ab-4b14-9a8a-d906b844baf5"
    asyncio.run(main(nb))
