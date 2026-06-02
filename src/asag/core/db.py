"""Async database connection pool and RLS helpers.

Usage:
    pool = await create_pool(cfg.require_db_url())
    async with pool.connection() as conn:
        await set_request_user(conn, user_id, org_id)
        # run queries with RLS active
    await pool.close()

In FastAPI (Session 9A), pool is managed via lifespan and injected via Depends.
"""

from __future__ import annotations

import logging
import uuid

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

log = logging.getLogger(__name__)


async def create_pool(
    db_url: str,
    *,
    min_size: int = 1,
    max_size: int = 10,
    timeout: float = 30.0,
) -> AsyncConnectionPool:
    """Open an async connection pool.

    Caller is responsible for calling ``await pool.close()`` when done.
    """
    pool = AsyncConnectionPool(
        conninfo=db_url,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        open=False,  # open manually so we control timing
    )
    await pool.open()
    log.debug("DB pool opened (min=%d, max=%d)", min_size, max_size)
    return pool


async def set_request_user(
    conn: AsyncConnection,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Set session-level vars read by RLS helper functions.

    Must be called at the start of every request that runs under user context.
    Server-side background tasks (ingestion pipeline, grader) do NOT call this —
    they connect with the service role key and bypass RLS intentionally.
    """
    await conn.execute(
        "SELECT set_config('app.current_user_id', %s, true)",
        (str(user_id),),
    )
    await conn.execute(
        "SELECT set_config('app.current_org_id', %s, true)",
        (str(org_id),),
    )
