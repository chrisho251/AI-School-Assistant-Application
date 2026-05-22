"""Unit tests for asag.config — no DB, no network."""

from __future__ import annotations

import pytest

from asag.config import ConfigError, Settings


def test_require_db_url_raises_when_empty() -> None:
    s = Settings(_env_file=None, supabase_db_url="")
    with pytest.raises(ConfigError, match="SUPABASE_DB_URL"):
        s.require_db_url()


def test_require_db_url_returns_value_when_set() -> None:
    s = Settings(_env_file=None, supabase_db_url="postgresql://x:y@h:5432/d")
    assert s.require_db_url() == "postgresql://x:y@h:5432/d"


def test_defaults_are_safe() -> None:
    s = Settings(_env_file=None)
    assert s.asag_env == "development"
    assert s.tei_embed_url.startswith("http://")
