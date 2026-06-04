"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from asag.config import Settings

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop not supported)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_llm: marks tests that call a real LLM API and consume quota "
        "(skipped by default — PowerShell: $env:ASAG_TEST_LIVE_LLM='1'; uv run pytest ...)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live_llm tests unless the caller opts in."""
    if os.getenv("ASAG_TEST_LIVE_LLM"):
        return  # opt-in: run everything
    skip = pytest.mark.skip(reason="live LLM test skipped — set ASAG_TEST_LIVE_LLM=1 to enable")
    for item in items:
        if item.get_closest_marker("live_llm"):
            item.add_marker(skip)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(asag_env="test")
