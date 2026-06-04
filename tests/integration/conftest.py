"""Shared fixtures for API integration tests (real Postgres, ASGI transport)."""

from __future__ import annotations

from collections.abc import AsyncIterator
import uuid

from httpx import ASGITransport, AsyncClient
import pytest

from asag.api.deps import get_pool
from asag.api.main import app
from asag.config import ConfigError, Settings, get_settings
from asag.core.db import create_pool


def dev_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    """Build a dev bearer token honoured when no JWT secret is configured."""
    return f"dev.{user_id}.{org_id}.{role}"


def auth_header(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {dev_token(user_id, org_id, role)}"}


@pytest.fixture
async def db_url() -> str:
    try:
        return get_settings().require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
async def api(db_url: str) -> AsyncIterator[AsyncClient]:
    """ASGI client backed by a real pool, with auth forced onto the dev-token path."""
    pool = await create_pool(db_url)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_settings] = lambda: Settings(
        asag_env="test", supabase_jwt_secret="", supabase_db_url=db_url
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await pool.close()
