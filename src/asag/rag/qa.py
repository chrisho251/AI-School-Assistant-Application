"""RAG Question-Answering chain — retrieve context, generate answer, persist conversation.

Entry points:
  answer(query, notebook_id, user_id, ...)        — blocking, returns AnswerResult
  stream_answer(query, notebook_id, user_id, ...)  — async generator yielding tokens
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
from pathlib import Path
import re
from typing import Any
import uuid

from psycopg_pool import AsyncConnectionPool

from asag.core.embeddings import EmbeddingClient
from asag.core.llm import astream_chat, chat
from asag.core.observability import traced
from asag.core.reranker import RerankClient
from asag.models.qa import AnswerResult, Citation
from asag.rag.retriever import ChunkResult, retrieve

log = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "qa.md").read_text()

# Matches [1], [2], [12] etc. in the model response
_REF_RE = re.compile(r"\[(\d+)\]")

REFUSAL_PHRASE = "The provided materials do not cover this topic."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_context(chunks: list[ChunkResult]) -> tuple[str, dict[int, ChunkResult]]:
    """Format chunks as numbered references; return context string + ref→chunk map."""
    ref_map: dict[int, ChunkResult] = {}
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        ref_map[i] = chunk
        page = f", page {chunk.page_number}" if chunk.page_number is not None else ""
        parts.append(f"[{i}] (source_id: {chunk.source_id}{page})\n{chunk.content}")
    return "\n\n".join(parts), ref_map


def _build_messages(query: str, context: str) -> list[dict[str, Any]]:
    """Compose the system + user messages for the QA prompt."""
    system = _SYSTEM_PROMPT_TEMPLATE.replace("{context}", context)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]


def _extract_citations(text: str, ref_map: dict[int, ChunkResult]) -> list[Citation]:
    """Parse [N] references from *text* into Citation objects, preserving order."""
    seen: set[int] = set()
    citations: list[Citation] = []
    for match in _REF_RE.finditer(text):
        n = int(match.group(1))
        if n in ref_map and n not in seen:
            seen.add(n)
            chunk = ref_map[n]
            citations.append(
                Citation(
                    source_id=chunk.source_id,
                    chunk_id=chunk.id,
                    page_number=chunk.page_number,
                )
            )
    return citations


async def _persist_exchange(
    notebook_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    query: str,
    response_text: str,
    citations: list[Citation],
    pool: AsyncConnectionPool,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Atomically create/reuse a conversation and insert user + assistant messages.

    Wrapping both operations in one connection ensures that a conversation row
    is never created without its accompanying messages (atomicity guarantee).

    Returns:
        ``(conversation_id, assistant_message_id)``
    """
    msg_id = uuid.uuid4()
    citations_json = json.dumps([c.model_dump(mode="json") for c in citations])

    async with pool.connection() as conn:
        if conversation_id is None:
            conversation_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO conversations (id, notebook_id, user_id) VALUES (%s, %s, %s)",
                (str(conversation_id), str(notebook_id), str(user_id)),
            )
            log.debug("Created conversation %s", conversation_id)

        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
            (str(conversation_id), "user", query),
        )
        await conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, citations) "
            "VALUES (%s, %s, %s, %s, %s::jsonb)",
            (str(msg_id), str(conversation_id), "assistant", response_text, citations_json),
        )

    return conversation_id, msg_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@traced("qa.answer")
async def answer(
    query: str,
    notebook_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    embed_client: EmbeddingClient,
    rerank_client: RerankClient,
    model: str,
    k_final: int = 5,
    conversation_id: uuid.UUID | None = None,
) -> AnswerResult:
    """Retrieve context, generate an answer, and persist the exchange.

    Args:
        query:           The student's question.
        notebook_id:     Notebook scope for retrieval and RLS.
        user_id:         Owner of the conversation.
        pool:            DB connection pool (RLS context set by caller).
        embed_client:    BGE-M3 client for query embedding.
        rerank_client:   bge-reranker client for re-ranking.
        model:           LiteLLM model string for the generator.
        k_final:         Number of chunks to pass to the LLM.
        conversation_id: Continue an existing conversation; None creates one.

    Returns:
        AnswerResult with the generated text, citations, and DB identifiers.
    """
    chunks = await retrieve(
        query,
        notebook_id,
        embed_client=embed_client,
        rerank_client=rerank_client,
        pool=pool,
        k_final=k_final,
    )

    context, ref_map = _build_context(chunks)
    messages = _build_messages(query, context)

    response_text = await chat(messages, model)

    citations = _extract_citations(response_text, ref_map)
    conv_id, msg_id = await _persist_exchange(
        notebook_id, user_id, conversation_id, query, response_text, citations, pool
    )

    log.debug(
        "answer: notebook=%s citations=%d refusal=%s",
        notebook_id,
        len(citations),
        response_text.strip() == REFUSAL_PHRASE,
    )
    return AnswerResult(
        answer=response_text,
        citations=citations,
        conversation_id=conv_id,
        message_id=msg_id,
    )


async def stream_answer(
    query: str,
    notebook_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    embed_client: EmbeddingClient,
    rerank_client: RerankClient,
    model: str,
    k_final: int = 5,
    conversation_id: uuid.UUID | None = None,
) -> AsyncGenerator[str, None]:
    """Stream answer tokens and persist the full exchange on completion.

    Args:
        query:           The student's question.
        notebook_id:     Notebook scope for retrieval and RLS.
        user_id:         Owner of the conversation.
        pool:            DB connection pool.
        embed_client:    BGE-M3 client.
        rerank_client:   Reranker client.
        model:           LiteLLM model string.
        k_final:         Chunks passed to the LLM.
        conversation_id: Continue an existing conversation; None creates one.

    Yields:
        Non-empty token strings as they arrive from the model.

    Note:
        DB persistence (conversations + messages rows) happens after the last
        token is yielded. If the generator is closed early the finally block
        still runs, saving whatever was accumulated.
    """
    chunks = await retrieve(
        query,
        notebook_id,
        embed_client=embed_client,
        rerank_client=rerank_client,
        pool=pool,
        k_final=k_final,
    )

    context, ref_map = _build_context(chunks)
    messages = _build_messages(query, context)

    full_answer = ""
    try:
        async for token in astream_chat(messages, model):
            full_answer += token
            yield token
    finally:
        if full_answer:
            citations = _extract_citations(full_answer, ref_map)
            await _persist_exchange(
                notebook_id, user_id, conversation_id, query, full_answer, citations, pool
            )
