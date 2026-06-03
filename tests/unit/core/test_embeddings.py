"""Unit tests for EmbeddingClient — TEI endpoints mocked via unittest.mock."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from asag.core.embeddings import EmbeddingClient, EmbeddingResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_DENSE = [
    [float(i) * 0.001 for i in range(1024)],
    [float(i) * 0.002 for i in range(1024)],
]
FAKE_SPARSE_RAW = [
    [{"index": 1, "value": 0.8}, {"index": 42, "value": 0.3}],
    [{"index": 7, "value": 0.5}],
]
EXPECTED_SPARSE = [{"1": 0.8, "42": 0.3}, {"7": 0.5}]


def _resp(data: object) -> MagicMock:
    """Build a mock HTTP response that returns *data* from .json()."""
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status = MagicMock()
    return r


def _make_mock_http(side_effects: list[object]) -> AsyncMock:
    """AsyncMock HTTP client whose post() returns successive *side_effects* on await."""
    mock_http = AsyncMock()
    mock_http.post.side_effect = [_resp(d) for d in side_effects]
    return mock_http


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_embed_texts_shape_with_sparse() -> None:
    """Returns one EmbeddingResult per input; dense shape and sparse dict correct."""
    mock_http = _make_mock_http([FAKE_DENSE, FAKE_SPARSE_RAW])
    with patch("asag.core.embeddings.httpx.AsyncClient", return_value=mock_http):
        client = EmbeddingClient("http://localhost:8080")
        results = await client.embed_texts(["hello", "world"])

    assert len(results) == 2
    assert all(isinstance(r, EmbeddingResult) for r in results)
    assert len(results[0].dense) == 1024
    assert results[0].sparse == EXPECTED_SPARSE[0]
    assert results[1].sparse == EXPECTED_SPARSE[1]


async def test_embed_texts_no_sparse() -> None:
    """return_sparse=False → single /embed call, sparse dicts are empty."""
    mock_http = _make_mock_http([FAKE_DENSE])
    with patch("asag.core.embeddings.httpx.AsyncClient", return_value=mock_http):
        client = EmbeddingClient("http://localhost:8080")
        results = await client.embed_texts(["hello", "world"], return_sparse=False)

    assert len(results) == 2
    assert results[0].sparse == {}
    assert results[1].sparse == {}
    mock_http.post.assert_called_once()  # Only /embed, not /embed_sparse


async def test_embed_texts_empty_input() -> None:
    """Empty input returns empty list without any HTTP calls."""
    client = EmbeddingClient("http://localhost:8080")
    results = await client.embed_texts([])
    assert results == []


async def test_embed_texts_http_error_propagates() -> None:
    """HTTPStatusError from TEI is re-raised to the caller."""
    bad = MagicMock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=MagicMock(),
    )
    mock_http = AsyncMock()
    mock_http.post.return_value = bad

    with patch("asag.core.embeddings.httpx.AsyncClient", return_value=mock_http):
        client = EmbeddingClient("http://localhost:8080")
        with pytest.raises(httpx.HTTPStatusError):
            await client.embed_texts(["hello"], return_sparse=False)


async def test_embed_texts_preserves_order() -> None:
    """Results are in the same order as inputs regardless of gather scheduling."""
    dense_a = [[0.1] * 1024]
    dense_b = [[0.9] * 1024]
    combined = [dense_a[0], dense_b[0]]
    # sparse endpoint returns one list per text
    mock_http = _make_mock_http([combined, [[], []]])
    with patch("asag.core.embeddings.httpx.AsyncClient", return_value=mock_http):
        client = EmbeddingClient("http://localhost:8080")
        results = await client.embed_texts(["a", "b"])

    assert results[0].dense[0] == pytest.approx(0.1)
    assert results[1].dense[0] == pytest.approx(0.9)
