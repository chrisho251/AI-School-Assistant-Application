"""FastAPI application entrypoint — wires the DB pool, shared clients, and routers.

Run: ``uv run uvicorn asag.api.main:app --reload`` then open ``/docs``.

The lifespan opens one connection pool and constructs the embedding/reranker/storage
clients once, stashing them on ``app.state`` for dependency injection. If the DB URL
is unset the pool is left as ``None`` (so tests can start the app without Postgres);
DB-backed routes will then fail fast at request time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from asag.api.routers import attempts, chat, notebooks, quizzes, sources
from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.core.embeddings import EmbeddingClient
from asag.core.reranker import RerankClient
from asag.core.storage import get_storage_backend

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared resources on startup; close them on shutdown."""
    cfg = get_settings()

    app.state.pool = None
    try:
        app.state.pool = await create_pool(cfg.require_db_url())
        log.info("DB pool opened")
    except ConfigError:
        log.warning("SUPABASE_DB_URL not set — DB-backed routes will be unavailable")

    app.state.embed_client = EmbeddingClient(cfg.tei_embed_url, timeout=cfg.tei_timeout)
    app.state.rerank_client = RerankClient(cfg.tei_rerank_url, timeout=cfg.tei_timeout)
    app.state.storage = None
    try:
        app.state.storage = get_storage_backend()
    except Exception:  # noqa: BLE001 — storage is optional until a source is uploaded
        log.warning("Storage backend unavailable — upload routes will fail until configured")

    try:
        yield
    finally:
        if app.state.pool is not None:
            await app.state.pool.close()
        await app.state.rerank_client.aclose()
        await app.state.embed_client._http.aclose()
        log.info("Shared resources closed")


app = FastAPI(title="ASAG API", version="0.1.0", lifespan=lifespan)

# Streamlit UI (Day 10+) runs on a different origin; allow it during the POC.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notebooks.router)
app.include_router(sources.router)
app.include_router(chat.router)
app.include_router(quizzes.router)
app.include_router(attempts.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe — does not touch the DB."""
    return {"status": "ok"}
