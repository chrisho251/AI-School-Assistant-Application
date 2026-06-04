"""Debug — run the RAG chat path (retrieve → stream) directly, printing tracebacks.

Usage:
    uv run python scripts/debug_chat.py <notebook_id> <user_id> "your question"
"""

from __future__ import annotations

import asyncio
import sys
import traceback
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(notebook_id: str, user_id: str, question: str) -> None:
    from asag.config import get_settings
    from asag.core.db import create_pool
    from asag.core.embeddings import EmbeddingClient
    from asag.core.reranker import RerankClient
    from asag.rag.qa import stream_answer
    from asag.rag.retriever import retrieve

    cfg = get_settings()
    pool = await create_pool(cfg.require_db_url())
    embed = EmbeddingClient(cfg.tei_embed_url, timeout=cfg.tei_timeout)
    rerank = RerankClient(cfg.tei_rerank_url, timeout=cfg.tei_timeout)
    nb = uuid.UUID(notebook_id)
    uid = uuid.UUID(user_id)

    print("\n[1] retrieve() ...")
    try:
        chunks = await retrieve(
            question, nb, embed_client=embed, rerank_client=rerank, pool=pool, k_final=5
        )
        print(f"    OK — {len(chunks)} chunks")
        for c in chunks[:2]:
            print(f"      - {c.id} p{c.page_number}: {c.content[:60]!r}")
    except Exception:
        print("    FAILED at retrieve():")
        traceback.print_exc()
        await pool.close()
        return

    print("\n[2] stream_answer() ...")
    try:
        full = ""
        async for tok in stream_answer(
            question,
            nb,
            uid,
            pool=pool,
            embed_client=embed,
            rerank_client=rerank,
            model=cfg.asag_llm_generator,
        ):
            full += tok
        print(f"    OK — {len(full)} chars")
        print(f"    Answer: {full[:300]!r}")
    except Exception:
        print("    FAILED at stream_answer():")
        traceback.print_exc()
    finally:
        await rerank.aclose()
        await embed._http.aclose()
        await pool.close()


if __name__ == "__main__":
    nb = sys.argv[1] if len(sys.argv) > 1 else "5e7c4b1a-55ab-4b14-9a8a-d906b844baf5"
    uid = sys.argv[2] if len(sys.argv) > 2 else "33333333-3333-3333-3333-333333333333"
    q = sys.argv[3] if len(sys.argv) > 3 else "What is this paper about?"
    asyncio.run(main(nb, uid, q))
