"""Observability hooks — @traced decorator stub.

No-op for POC; swap body with Langfuse @observe in Phase 9 by replacing the
return value of ``traced()`` with the Langfuse decorator.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import functools
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def traced(name: str | None = None) -> Callable[[F], F]:  # noqa: ARG001
    """No-op decorator marking a function for future Langfuse tracing.

    Args:
        name: Optional span name override; defaults to the function name.

    Usage::

        @traced("my_span")
        async def my_function(...):
            ...
    """

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
