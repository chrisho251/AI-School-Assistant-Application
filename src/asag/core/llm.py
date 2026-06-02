"""LiteLLM wrapper — single interface for all LLM calls.

Session 2C: chat_sync() + async chat() with multimodal (image) support.
Session 5A will add: astream_chat(), structured_output(), @traced decorator.

All provider API keys are pushed to os.environ at import time so LiteLLM can
find them whether they came from .env or the process environment.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import litellm
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
litellm._async_success_callback = []  # type: ignore[attr-defined]
litellm._async_failure_callback = []  # type: ignore[attr-defined]


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


@_retry
async def chat(
    messages: list[dict[str, Any]],
    model: str,
    *,
    images: list[ImagePayload] | None = None,
    temperature: float = 0.2,
) -> str:
    """Non-blocking LLM call — use inside async request handlers."""
    msgs = _build_messages(messages, images)
    log.debug("chat model=%s images=%d", model, len(images or []))
    response = await litellm.acompletion(model=model, messages=msgs, temperature=temperature)
    return str(response.choices[0].message.content)


# TODO Session 5A: astream_chat() — yields token chunks for SSE
# TODO Session 5A: structured_output(response_schema) — Pydantic model output
# TODO Session 9A: @traced decorator — Langfuse observability hook
