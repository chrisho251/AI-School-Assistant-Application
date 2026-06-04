"""RAG chat over a notebook, streamed to the client as Server-Sent Events.

``GET /chat/{notebook_id}?q=...`` authorizes the notebook under RLS, then streams
answer tokens from ``rag.qa.stream_answer``. The conversation + messages rows are
persisted by the streaming generator once the final token is emitted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg_pool import AsyncConnectionPool
from sse_starlette.sse import EventSourceResponse

from asag.api.deps import (
    AuthContext,
    get_embed_client,
    get_pool,
    get_rerank_client,
    rls_connection,
    verify_jwt,
)
from asag.config import get_settings
from asag.core.embeddings import EmbeddingClient
from asag.core.reranker import RerankClient
from asag.ingestion.repository import NotebookRepository
from asag.rag.qa import stream_answer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{notebook_id}")
async def chat_stream(
    notebook_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="The student's question"),
    conversation_id: uuid.UUID | None = Query(None),
    auth: AuthContext = Depends(verify_jwt),
    pool: AsyncConnectionPool = Depends(get_pool),
    embed_client: EmbeddingClient = Depends(get_embed_client),
    rerank_client: RerankClient = Depends(get_rerank_client),
) -> EventSourceResponse:
    """Stream a cited answer for *q* grounded in *notebook_id*'s chunks.

    Authorization happens up front via a short RLS-scoped check so the pooled
    connection is released before the (potentially long) token stream begins.
    """
    async with rls_connection(pool, auth) as conn:
        if await NotebookRepository(conn).get_by_id(notebook_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")

    model = get_settings().asag_llm_generator

    async def event_source() -> AsyncIterator[dict[str, str]]:
        # Emit a structured 'error' event on failure rather than letting the
        # exception abruptly drop the SSE connection (which clients see as a
        # truncated stream). The answer itself is persisted by stream_answer.
        try:
            async for token in stream_answer(
                q,
                notebook_id,
                auth.user_id,
                pool=pool,
                embed_client=embed_client,
                rerank_client=rerank_client,
                model=model,
                conversation_id=conversation_id,
            ):
                yield {"event": "token", "data": token}
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client
            log.exception("chat stream failed for notebook %s", notebook_id)
            yield {"event": "error", "data": f"{type(exc).__name__}: {exc}"}
            return
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_source())
