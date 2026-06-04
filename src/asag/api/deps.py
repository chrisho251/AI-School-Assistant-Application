"""FastAPI dependencies — JWT auth, RLS-scoped DB connections, shared clients.

Auth flow: the bearer token's ``sub`` claim identifies the user; ``org_id`` and
``role`` are read from the ``users`` table (not trusted from the token). ``get_db``
yields a connection pinned to the non-superuser ``asag_app`` role with the RLS
session GUCs set, so every query in a request is filtered by the DB policies.

Heavy domain orchestrators (qa, quiz, grading) instead receive the raw pool and
run as the service role — they enforce access via explicit notebook/owner filters.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from asag.api.security import JWTError, decode_hs256
from asag.config import Settings, get_settings
from asag.core.embeddings import EmbeddingClient
from asag.core.reranker import RerankClient
from asag.core.storage import StorageBackend

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


class AuthContext(BaseModel):
    """Authenticated caller identity, resolved once per request."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"


# --------------------------------------------------------------------------- #
# App-state accessors (populated in main.py lifespan)                          #
# --------------------------------------------------------------------------- #


def get_pool(request: Request) -> AsyncConnectionPool:
    """Return the shared DB pool from app state."""
    return request.app.state.pool  # type: ignore[no-any-return]


def get_storage(request: Request) -> StorageBackend:
    """Return the shared storage backend from app state."""
    return request.app.state.storage  # type: ignore[no-any-return]


def get_embed_client(request: Request) -> EmbeddingClient:
    """Return the shared embedding client from app state."""
    return request.app.state.embed_client  # type: ignore[no-any-return]


def get_rerank_client(request: Request) -> RerankClient:
    """Return the shared reranker client from app state."""
    return request.app.state.rerank_client  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Authentication                                                               #
# --------------------------------------------------------------------------- #


def _parse_dev_token(token: str) -> AuthContext | None:
    """Decode a ``dev.<user_id>.<org_id>.<role>`` token; None if not that shape.

    Only honoured when no JWT secret is configured and env is development/test —
    lets Chris exercise the API with curl without minting real Supabase tokens.
    """
    if not token.startswith("dev."):
        return None
    parts = token.split(".")
    if len(parts) != 4:
        return None
    try:
        return AuthContext(user_id=uuid.UUID(parts[1]), org_id=uuid.UUID(parts[2]), role=parts[3])
    except ValueError:
        return None


async def _lookup_user(pool: AsyncConnectionPool, user_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Return ``(org_id, role)`` for *user_id* via the service role; 401 if unknown."""
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT org_id, role FROM users WHERE id = %s", (str(user_id),))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return uuid.UUID(str(row[0])), str(row[1])


async def verify_jwt(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Authenticate the bearer token and resolve the caller's org + role.

    Raises:
        HTTPException 401: missing/invalid token, or user not in the DB.
    """
    token = creds.credentials

    dev_ok = not settings.supabase_jwt_secret and settings.asag_env in {"development", "test"}
    if dev_ok and (ctx := _parse_dev_token(token)) is not None:
        return ctx

    if not settings.supabase_jwt_secret:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "JWT secret not configured")

    try:
        claims = decode_hs256(token, settings.supabase_jwt_secret)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing 'sub' claim")
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "'sub' is not a valid UUID") from exc

    org_id, role = await _lookup_user(pool, user_id)
    return AuthContext(user_id=user_id, org_id=org_id, role=role)


def require_teacher(auth: AuthContext = Depends(verify_jwt)) -> AuthContext:
    """Authorize teacher-only routes; 403 for students."""
    if not auth.is_teacher:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teacher role required")
    return auth


# --------------------------------------------------------------------------- #
# RLS-scoped DB connection                                                     #
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def rls_connection(
    pool: AsyncConnectionPool, auth: AuthContext
) -> AsyncIterator[AsyncConnection]:
    """Acquire a pool connection pinned to ``asag_app`` with this caller's RLS GUCs.

    The body runs in one transaction; ``SET LOCAL`` + ``set_config(..., true)`` reset
    at transaction end so the connection returns to the pool clean. Use this directly
    in streaming routes that must release the connection before the response body is
    produced; request-scoped routes use the ``get_db`` dependency instead.
    """
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SET LOCAL ROLE asag_app")
        await conn.execute(
            "SELECT set_config('app.current_user_id', %s, true)", (str(auth.user_id),)
        )
        await conn.execute("SELECT set_config('app.current_org_id', %s, true)", (str(auth.org_id),))
        yield conn


async def get_db(
    auth: AuthContext = Depends(verify_jwt),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> AsyncIterator[AsyncConnection]:
    """Yield an RLS-scoped connection for a request (commit/rollback auto-managed)."""
    async with rls_connection(pool, auth) as conn:
        yield conn
