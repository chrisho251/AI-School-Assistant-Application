"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from asag.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(asag_env="test")
