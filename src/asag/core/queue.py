"""Task queue interface — POC backs it with FastAPI BackgroundTasks.

The ``enqueue`` interface is the extensibility hook (plan.md §8): swapping in a
real queue (Inngest / arq) later means implementing ``TaskQueue`` and selecting it
via ``QUEUE_BACKEND`` — no caller changes. For the POC, ``BackgroundTaskQueue``
defers a coroutine to run after the HTTP response is sent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from starlette.background import BackgroundTasks

log = logging.getLogger(__name__)


class TaskQueue(ABC):
    """Abstract deferred-execution interface for background work."""

    @abstractmethod
    def enqueue(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> None:
        """Schedule *func(\\*args, \\*\\*kwargs)* to run out of the request path."""


class BackgroundTaskQueue(TaskQueue):
    """POC queue: wraps a per-request Starlette ``BackgroundTasks`` instance.

    Args:
        background_tasks: The request's ``BackgroundTasks`` (FastAPI injects one).

    Usage::

        queue = BackgroundTaskQueue(background_tasks)
        queue.enqueue(ingest_source, source_id, pool=pool, storage=storage)
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._bg = background_tasks

    def enqueue(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> None:
        # Starlette awaits coroutine-returning callables after the response flushes.
        self._bg.add_task(func, *args, **kwargs)
        log.debug("enqueued %s (args=%d kwargs=%d)", func.__name__, len(args), len(kwargs))
