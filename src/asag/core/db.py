"""Database connection helpers. Filled in during Phase 1."""

from __future__ import annotations

# TODO D04: connection pool (psycopg_pool.AsyncConnectionPool)
# TODO D04: helper get_db() yielding a connection scoped to a request/user
# TODO D07: helper set_request_user(conn, user_id, org_id) — sets postgres
#           `set_config('request.jwt.claims', ...)` so RLS sees the user.
