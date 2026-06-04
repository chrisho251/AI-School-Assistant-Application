"""Unit tests for the BackgroundTaskQueue adapter."""

from __future__ import annotations

from starlette.background import BackgroundTasks

from asag.core.queue import BackgroundTaskQueue


async def _noop(x: int, *, y: int) -> None:  # pragma: no cover - body never run here
    pass


def test_enqueue_registers_task_with_args() -> None:
    bg = BackgroundTasks()
    queue = BackgroundTaskQueue(bg)

    queue.enqueue(_noop, 1, y=2)

    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    assert task.func is _noop
    assert task.args == (1,)
    assert task.kwargs == {"y": 2}
