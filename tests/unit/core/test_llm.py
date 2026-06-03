"""Unit tests for llm.py — LiteLLM wrapper (mocked)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from asag.core.llm import astream_chat, chat, structured_output

# ---------------------------------------------------------------------------
# Helpers — build fake litellm response objects
# ---------------------------------------------------------------------------


def _fake_completion(content: str) -> MagicMock:
    """Build a non-streaming litellm response mock."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _fake_stream_chunk(content: str | None) -> MagicMock:
    """Build one streaming chunk mock."""
    delta = MagicMock()
    delta.content = content
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


class _FakeAsyncStream:
    """Async iterable over a list of pre-built chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self._idx = 0

    def __aiter__(self) -> _FakeAsyncStream:
        return self

    async def __anext__(self) -> Any:
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        val = self._chunks[self._idx]
        self._idx += 1
        return val


# ---------------------------------------------------------------------------
# Tests — chat()
# ---------------------------------------------------------------------------


async def test_chat_returns_content() -> None:
    """chat() returns the assistant message content string."""
    fake = _fake_completion("42 is the answer")
    with patch("asag.core.llm.litellm.acompletion", new=AsyncMock(return_value=fake)):
        result = await chat([{"role": "user", "content": "2+2"}], model="gemini/gemini-2.5-flash")

    assert result == "42 is the answer"


async def test_chat_passes_model_and_messages() -> None:
    """chat() forwards model and messages to litellm.acompletion."""
    fake = _fake_completion("ok")
    mock_acompletion = AsyncMock(return_value=fake)
    with patch("asag.core.llm.litellm.acompletion", new=mock_acompletion):
        await chat([{"role": "user", "content": "hi"}], model="groq/llama-3.3-70b-versatile")

    call_kwargs = mock_acompletion.call_args
    assert call_kwargs.kwargs["model"] == "groq/llama-3.3-70b-versatile"
    assert call_kwargs.kwargs["messages"][0]["content"] == "hi"


# ---------------------------------------------------------------------------
# Tests — astream_chat()
# ---------------------------------------------------------------------------


async def test_astream_chat_yields_tokens() -> None:
    """astream_chat() yields each non-empty delta.content."""
    chunks = [
        _fake_stream_chunk("Hello"),
        _fake_stream_chunk(" world"),
        _fake_stream_chunk(None),  # trailing None — must be skipped
        _fake_stream_chunk("!"),
    ]
    mock_acompletion = AsyncMock(return_value=_FakeAsyncStream(chunks))
    with patch("asag.core.llm.litellm.acompletion", new=mock_acompletion):
        tokens = [
            tok
            async for tok in astream_chat(
                [{"role": "user", "content": "hi"}],
                model="gemini/gemini-2.5-flash",
            )
        ]

    assert tokens == ["Hello", " world", "!"]


async def test_astream_chat_empty_stream_yields_nothing() -> None:
    """astream_chat() with zero chunks produces an empty sequence."""
    mock_acompletion = AsyncMock(return_value=_FakeAsyncStream([]))
    with patch("asag.core.llm.litellm.acompletion", new=mock_acompletion):
        tokens = [
            tok
            async for tok in astream_chat(
                [{"role": "user", "content": "hi"}],
                model="gemini/gemini-2.5-flash",
            )
        ]

    assert tokens == []


async def test_astream_chat_passes_stream_true() -> None:
    """astream_chat() must pass stream=True to litellm."""
    mock_acompletion = AsyncMock(return_value=_FakeAsyncStream([]))
    with patch("asag.core.llm.litellm.acompletion", new=mock_acompletion):
        _ = [
            tok
            async for tok in astream_chat(
                [{"role": "user", "content": "hi"}],
                model="gemini/gemini-2.5-flash",
            )
        ]

    assert mock_acompletion.call_args.kwargs.get("stream") is True


# ---------------------------------------------------------------------------
# Tests — structured_output()
# ---------------------------------------------------------------------------


class _Answer(BaseModel):
    value: int
    explanation: str


async def test_structured_output_parses_json() -> None:
    """structured_output() parses JSON response into the given Pydantic schema."""
    fake = _fake_completion('{"value": 42, "explanation": "because"}')
    with patch("asag.core.llm.litellm.acompletion", new=AsyncMock(return_value=fake)):
        result = await structured_output(
            [{"role": "user", "content": "what?"}],
            model="gemini/gemini-2.5-flash",
            response_schema=_Answer,
        )

    assert isinstance(result, _Answer)
    assert result.value == 42
    assert result.explanation == "because"


async def test_structured_output_strips_code_fence() -> None:
    """structured_output() handles responses wrapped in markdown code fences."""
    fenced = '```json\n{"value": 7, "explanation": "lucky"}\n```'
    fake = _fake_completion(fenced)
    with patch("asag.core.llm.litellm.acompletion", new=AsyncMock(return_value=fake)):
        result = await structured_output(
            [{"role": "user", "content": "what?"}],
            model="gemini/gemini-2.5-flash",
            response_schema=_Answer,
        )

    assert result.value == 7


async def test_structured_output_passes_response_format() -> None:
    """structured_output() forwards response_schema as response_format to litellm."""
    fake = _fake_completion('{"value": 1, "explanation": "one"}')
    mock_acompletion = AsyncMock(return_value=fake)
    with patch("asag.core.llm.litellm.acompletion", new=mock_acompletion):
        await structured_output(
            [{"role": "user", "content": "?"}],
            model="gemini/gemini-2.5-flash",
            response_schema=_Answer,
        )

    assert mock_acompletion.call_args.kwargs["response_format"] is _Answer


# ---------------------------------------------------------------------------
# Tests — observability stub
# ---------------------------------------------------------------------------


def test_traced_preserves_sync_function() -> None:
    """@traced wraps a sync function without changing its return value."""
    from asag.core.observability import traced

    @traced("my_span")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


async def test_traced_preserves_async_function() -> None:
    """@traced wraps an async function without changing its return value."""
    from asag.core.observability import traced

    @traced()
    async def mul(a: int, b: int) -> int:
        return a * b

    assert await mul(3, 4) == 12
