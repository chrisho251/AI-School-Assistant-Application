"""Debug — run the real ingest_source() path (storage download → parse → embed).

Reuses an existing (failed) source row so it exercises the exact API code path,
printing the full traceback instead of the swallowed error_message.

Usage:
    $env:PYTHONIOENCODING="utf-8"; uv run python scripts/debug_ingest_api.py <source_id>
"""

from __future__ import annotations

import asyncio
import sys
import traceback

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(source_id_str: str) -> None:
    import uuid

    from asag.config import get_settings
    from asag.core.db import create_pool
    from asag.core.storage import get_storage_backend
    from asag.ingestion.pipeline import ingest_source

    cfg = get_settings()
    pool = await create_pool(cfg.require_db_url())
    storage = get_storage_backend()
    source_id = uuid.UUID(source_id_str)

    # Reset status so the idempotency guard doesn't skip a non-'ready' source.
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE sources SET ingestion_status='pending' WHERE id=%s", (str(source_id),)
        )
        await conn.commit()

    print(f"\nRunning ingest_source({source_id}) ...")
    try:
        result = await ingest_source(source_id, pool=pool, storage=storage)
        print(f"OK ✅ — {result}")
    except Exception:
        print("FAILED — full traceback:\n")
        traceback.print_exc()
    finally:
        await pool.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: debug_ingest_api.py <source_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
