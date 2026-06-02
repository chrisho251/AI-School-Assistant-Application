"""Async HTTP client for Text Embeddings Inference (TEI) — BGE-M3.

TEI exposes two relevant endpoints:
  POST /embed           → list[list[float]]           dense vectors (1024-d for BGE-M3)
  POST /embed_sparse    → list[list[{index, value}]]  sparse token weights (SPLADE-style)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Dense + optional sparse vectors for one text input."""

    dense: list[float]
    # str(token_id) → weight; empty dict means no sparse data available
    sparse: dict[str, float] = field(default_factory=dict)


class EmbeddingClient:
    """Async client wrapping one TEI embedding server instance.

    Usage::

        client = EmbeddingClient("http://localhost:8080")
        results = await client.embed_texts(["sentence one", "sentence two"])
        dense_vec = results[0].dense   # list[float] length 1024
        sparse_map = results[0].sparse # dict[str, float]
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def embed_texts(
        self,
        texts: list[str],
        *,
        return_sparse: bool = True,
    ) -> list[EmbeddingResult]:
        """Embed a batch of texts in one or two concurrent HTTP calls.

        Args:
            texts: Strings to embed. Empty list returns immediately.
            return_sparse: When True, fires /embed_sparse concurrently with
                /embed and attaches the resulting token weights.

        Returns:
            One EmbeddingResult per input text, preserving input order.

        Raises:
            httpx.HTTPStatusError: If TEI returns a non-2xx status.
        """
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            if return_sparse:
                dense_resp, sparse_resp = await asyncio.gather(
                    http.post(f"{self._base}/embed", json={"inputs": texts}),
                    http.post(f"{self._base}/embed_sparse", json={"inputs": texts}),
                )
                dense_resp.raise_for_status()
                dense_vecs: list[list[float]] = dense_resp.json()

                # 424 = model/backend doesn't support sparse (e.g. ONNX without sparse head)
                if sparse_resp.status_code == 424:
                    log.warning(
                        "TEI /embed_sparse returned 424 — sparse not supported by this "
                        "model backend; storing dense-only embeddings."
                    )
                    sparses: list[dict[str, float]] = [{} for _ in texts]
                else:
                    sparse_resp.raise_for_status()
                    raw_sparse: list[list[dict[str, Any]]] = sparse_resp.json()
                    sparses = [
                        {str(tok["index"]): float(tok["value"]) for tok in toks}
                        for toks in raw_sparse
                    ]
            else:
                resp = await http.post(f"{self._base}/embed", json={"inputs": texts})
                resp.raise_for_status()
                dense_vecs = resp.json()
                sparses = [{} for _ in texts]

        log.debug("Embedded %d texts (return_sparse=%s)", len(texts), return_sparse)
        return [
            EmbeddingResult(dense=d, sparse=s) for d, s in zip(dense_vecs, sparses, strict=True)
        ]
