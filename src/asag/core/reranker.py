"""Async HTTP client for TEI bge-reranker-v2-m3.

TEI exposes POST /rerank which takes a query + list of texts and returns
per-document relevance scores sorted by the server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Score + original input index for one reranked document."""

    index: int
    score: float
    text: str = field(default="")


class RerankClient:
    """Async client wrapping one TEI reranker server instance.

    Args:
        base_url: Full URL of the TEI reranker server, e.g. ``http://localhost:8081``.
        timeout: Per-request timeout in seconds.

    Usage::

        client = RerankClient("http://localhost:8081")
        results = await client.rerank("my query", ["doc1", "doc2"], top_n=5)
        best = results[0]   # highest relevance score
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=timeout)

    async def rerank(
        self,
        query: str,
        texts: list[str],
        *,
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """Rerank texts by relevance to query.

        Args:
            query: The query string.
            texts: Documents to rerank (input order preserved in ``index`` field).
            top_n: Return only the top N results; None returns all, sorted desc.

        Returns:
            RerankResult list sorted by score descending.

        Raises:
            httpx.HTTPStatusError: If TEI returns a non-2xx status.
        """
        if not texts:
            return []

        resp = await self._http.post(
            f"{self._base}/rerank",
            json={"query": query, "texts": texts},
        )
        resp.raise_for_status()

        raw: list[dict[str, Any]] = resp.json()
        results = [
            RerankResult(
                index=int(r["index"]),
                score=float(r["score"]),
                text=str(r.get("text", "")),
            )
            for r in raw
        ]
        results.sort(key=lambda r: r.score, reverse=True)

        if top_n is not None:
            results = results[:top_n]

        log.debug("Reranked %d texts → returned %d", len(texts), len(results))
        return results

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
