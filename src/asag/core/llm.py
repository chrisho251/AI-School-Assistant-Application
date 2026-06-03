"""LiteLLM wrapper — single interface for all LLM calls.

All provider API keys are pushed to os.environ at import time so LiteLLM can
find them whether they came from .env or the process environment.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator
import logging
import os
import re
from typing import Any

import litellm
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from asag.config import get_settings

log = logging.getLogger(__name__)

# Suppress noisy LiteLLM debug output unless the app is in debug mode
litellm.suppress_debug_info = True
# Disable async logging callbacks — Langfuse observability is deferred to Phase 9.
# Without this, LiteLLM's LoggingWorker leaves unawaited coroutines when the
# asyncio event loop closes (e.g. at end of each pytest test), producing
# RuntimeWarning: coroutine 'Logging.async_success_handler' was never awaited.
litellm.success_callback = []
litellm.failure_callback = []
litellm._async_success_callback = []
litellm._async_failure_callback = []


def _init_api_keys() -> None:
    """Push provider keys from Settings into os.environ for LiteLLM."""
    cfg = get_settings()
    if cfg.gemini_api_key:
        os.environ.setdefault("GEMINI_API_KEY", cfg.gemini_api_key)
    if cfg.groq_api_key:
        os.environ.setdefault("GROQ_API_KEY", cfg.groq_api_key)
    if cfg.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", cfg.openrouter_api_key)


_init_api_keys()


# --------------------------------------------------------------------------- #
# Retry policy — handles transient 503/429 from Gemini and Groq               #
# --------------------------------------------------------------------------- #


def _is_transient(exc: BaseException) -> bool:
    """Return True for rate-limit or server overload errors worth retrying."""
    msg = str(exc).lower()
    return any(code in msg for code in ("503", "429", "rate limit", "unavailable", "overloaded"))


_retry = retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)


# --------------------------------------------------------------------------- #
# Message builder                                                              #
# --------------------------------------------------------------------------- #

ImagePayload = tuple[bytes, str]  # (raw_bytes, mime_type)


def _build_messages(
    messages: list[dict[str, Any]],
    images: list[ImagePayload] | None = None,
) -> list[dict[str, Any]]:
    """Inject base64-encoded images into the last message's content list.

    If the last message content is a plain string, it is converted to the
    OpenAI multi-part content format before images are appended.
    """
    if not images:
        return messages

    result = list(messages)
    last = dict(result[-1])
    content: list[dict[str, Any]]

    if isinstance(last.get("content"), str):
        content = [{"type": "text", "text": last["content"]}]
    else:
        content = list(last.get("content", []))

    for raw, mime in images:
        b64 = base64.b64encode(raw).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    last["content"] = content
    result[-1] = last
    return result


# --------------------------------------------------------------------------- #
# Sync interface (used by loaders — parse() is a sync method)                 #
# --------------------------------------------------------------------------- #


@_retry
def chat_sync(
    messages: list[dict[str, Any]],
    model: str,
    *,
    images: list[ImagePayload] | None = None,
    temperature: float = 0.2,
) -> str:
    """Blocking LLM call — use inside sync code (e.g. Loader.parse).

    Args:
        messages:    Standard OpenAI-format messages list.
        model:       LiteLLM model string e.g. "gemini/gemini-2.5-flash".
        images:      Optional list of (bytes, mime_type) to attach as vision input.
        temperature: Sampling temperature (lower = more deterministic).

    Returns:
        The assistant message content as a plain string.
    """
    msgs = _build_messages(messages, images)
    log.debug("chat_sync model=%s images=%d", model, len(images or []))
    response = litellm.completion(model=model, messages=msgs, temperature=temperature)
    return str(response.choices[0].message.content)


# --------------------------------------------------------------------------- #
# Async interface (used by RAG Q&A, assessment — Session 5A+)                 #
# --------------------------------------------------------------------------- #

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_fence(text: str) -> str:
    """Remove markdown code fences from JSON responses if present."""
    m = _JSON_FENCE_RE.match(text.strip())
    return m.group(1) if m else text


@_retry
async def chat(
    messages: list[dict[str, Any]],
    model: str,
    *,
    images: list[ImagePayload] | None = None,
    temperature: float = 0.2,
) -> str:
    """Non-blocking LLM call — use inside async request handlers.

    Args:
        messages:    Standard OpenAI-format messages list.
        model:       LiteLLM model string e.g. "gemini/gemini-2.5-flash".
        images:      Optional list of (bytes, mime_type) to attach as vision input.
        temperature: Sampling temperature.

    Returns:
        The assistant message content as a plain string.
    """
    msgs = _build_messages(messages, images)
    log.debug("chat model=%s images=%d", model, len(images or []))
    response = await litellm.acompletion(model=model, messages=msgs, temperature=temperature)
    return str(response.choices[0].message.content)


async def astream_chat(
    messages: list[dict[str, Any]],
    model: str,
    *,
    images: list[ImagePayload] | None = None,
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    """Stream LLM response token-by-token for SSE delivery.

    Args:
        messages:    Standard OpenAI-format messages list.
        model:       LiteLLM model string.
        images:      Optional vision attachments.
        temperature: Sampling temperature.

    Yields:
        Non-empty token strings as they arrive from the model.

    Raises:
        httpx.HTTPStatusError / litellm exceptions on provider errors.
    """
    msgs = _build_messages(messages, images)
    log.debug("astream_chat model=%s images=%d", model, len(images or []))
    response = await litellm.acompletion(
        model=model, messages=msgs, temperature=temperature, stream=True
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


@_retry
async def structured_output[T: BaseModel](
    messages: list[dict[str, Any]],
    model: str,
    response_schema: type[T],
    *,
    temperature: float = 0.1,
) -> T:
    """Call LLM and parse the JSON response as a Pydantic model.

    Args:
        messages:        Standard OpenAI-format messages list.
        model:           LiteLLM model string.
        response_schema: Pydantic BaseModel subclass to parse into.
        temperature:     Lower temperature for structured tasks.

    Returns:
        An instance of *response_schema* validated from the model's JSON output.

    Raises:
        ValueError:            If the model returns no text content (e.g. tool-call only mode).
        pydantic.ValidationError: If the model returns invalid or unexpected JSON.
    """
    log.debug("structured_output model=%s schema=%s", model, response_schema.__name__)
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        response_format=response_schema,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if content is None:
        # Some backends return structured data in .parsed / tool_calls rather than
        # .content — raise explicitly so the caller gets a clear error rather than
        # a confusing "invalid JSON: 'None'" further down.
        raise ValueError(
            f"structured_output: model returned no text content "
            f"(schema={response_schema.__name__}, model={model})"
        )
    raw = _strip_fence(content)
    return response_schema.model_validate_json(raw)


# TODO D09: @traced decorator — Langfuse observability hook
