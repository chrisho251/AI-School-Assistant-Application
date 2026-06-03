"""Unit tests for RerankClient — TEI /rerank endpoint mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from asag.core.reranker import RerankClient


def _mock_resp(data: object) -> MagicMock:
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status = MagicMock()
    return r


def _make_mock_http(response_data: object) -> AsyncMock:
    """AsyncMock HTTP client whose post() returns *response_data* on await."""
    mock_http = AsyncMock()
    mock_http.post.return_value = _mock_resp(response_data)
    return mock_http


async def test_rerank_returns_sorted_results() -> None:
    """Results are sorted by score descending regardless of server order."""
    raw = [
        {"index": 0, "score": 0.3},
        {"index": 1, "score": 0.9},
        {"index": 2, "score": 0.6},
    ]
    mock_http = _make_mock_http(raw)
    with patch("asag.core.reranker.httpx.AsyncClient", return_value=mock_http):
        client = RerankClient("http://localhost:8081")
        results = await client.rerank("q", ["a", "b", "c"])

    assert [r.score for r in results] == pytest.approx([0.9, 0.6, 0.3])
    assert [r.index for r in results] == [1, 2, 0]


async def test_rerank_top_n_truncates() -> None:
    """top_n=2 returns only the 2 highest-scored items."""
    raw = [{"index": i, "score": float(i) * 0.1} for i in range(5)]
    mock_http = _make_mock_http(raw)
    with patch("asag.core.reranker.httpx.AsyncClient", return_value=mock_http):
        client = RerankClient("http://localhost:8081")
        results = await client.rerank("q", [f"doc{i}" for i in range(5)], top_n=2)

    assert len(results) == 2
    assert results[0].score >= results[1].score


async def test_rerank_empty_input_returns_empty() -> None:
    """Empty texts list returns empty list without HTTP calls."""
    client = RerankClient("http://localhost:8081")
    results = await client.rerank("q", [])
    assert results == []


async def test_rerank_http_error_propagates() -> None:
    """HTTPStatusError from TEI is re-raised."""
    bad = MagicMock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    mock_http = AsyncMock()
    mock_http.post.return_value = bad

    with patch("asag.core.reranker.httpx.AsyncClient", return_value=mock_http):
        client = RerankClient("http://localhost:8081")
        with pytest.raises(httpx.HTTPStatusError):
            await client.rerank("q", ["doc"])
