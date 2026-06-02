"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
import sys

import pytest

from asag.config import Settings

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop not supported)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def test_settings() -> Settings:
    return Settings(asag_env="test")
