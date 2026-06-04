"""Integration test for the slide-generation orchestrator.

Real Postgres (chunks seeded + artifact row persisted); the LLM outline call and
the Marp subprocess are mocked, and storage is an in-memory fake. Verifies the
end-to-end pipeline writes a ``ready`` artifact row with a file URL + grounded
outline payload, and uploads one file per requested format.

A real Marp render is a manual verify (see day-8 test notes), not part of CI.

Run:
    uv run pytest tests/integration/test_slides.py -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
import uuid

import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.core.storage import StorageBackend
from asag.studio.outline import _OutlineDraft, _SlideDraft


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


class _FakeStorage(StorageBackend):
    """In-memory StorageBackend — records uploads, returns deterministic URLs."""

    def __init__(self) -> None:
        self.uploaded: dict[str, tuple[bytes, str]] = {}

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self.uploaded[key] = (data, content_type)
        return f"https://fake.storage/{key}"

    async def download(self, key: str) -> bytes:
        return self.uploaded[key][0]

    async def delete(self, key: str) -> None:
        self.uploaded.pop(key, None)

    async def get_public_url(self, key: str) -> str:
        return f"https://fake.storage/{key}"


class _Ids:
    def __init__(self) -> None:
        self.org = uuid.uuid4()
        self.user = uuid.uuid4()
        self.class_ = uuid.uuid4()
        self.notebook = uuid.uuid4()
        self.source = uuid.uuid4()
        self.chunk_a = uuid.uuid4()
        self.chunk_b = uuid.uuid4()


async def _seed(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(ids.org), "Slides Org", f"sl-{ids.org.hex[:8]}"),
        )
        await conn.execute(
            "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
            (str(ids.user), str(ids.org), "sl@test.com", "SL Teacher", "teacher"),
        )
        await conn.execute(
            "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
            (str(ids.class_), str(ids.org), "SL Class", str(ids.user)),
        )
        await conn.execute(
            "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
            (str(ids.notebook), str(ids.class_), str(ids.user), "SL Notebook"),
        )
        await conn.execute(
            "INSERT INTO sources (id, notebook_id, source_type, original_filename, "
            "storage_url, ingestion_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(ids.source), str(ids.notebook), "pdf", "sl.pdf", "test/sl.pdf", "ready"),
        )
        for chunk_id, ordinal, content in [
            (ids.chunk_a, 0, "Photosynthesis converts light energy into chemical energy."),
            (ids.chunk_b, 1, "The Calvin cycle fixes carbon dioxide into glucose."),
        ]:
            await conn.execute(
                "INSERT INTO chunks (id, source_id, notebook_id, ordinal, content_type, content, "
                "metadata) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (str(chunk_id), str(ids.source), str(ids.notebook), ordinal, "text", content, "{}"),
            )
        await conn.commit()


async def _cleanup(db_url: str, ids: _Ids) -> None:
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute("DELETE FROM artifacts WHERE notebook_id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM chunks WHERE source_id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM sources WHERE id = %s", (str(ids.source),))
        await conn.execute("DELETE FROM notebooks WHERE id = %s", (str(ids.notebook),))
        await conn.execute("DELETE FROM classes WHERE id = %s", (str(ids.class_),))
        await conn.execute("DELETE FROM users WHERE id = %s", (str(ids.user),))
        await conn.execute("DELETE FROM organizations WHERE id = %s", (str(ids.org),))
        await conn.commit()


def _outline_draft() -> _OutlineDraft:
    return _OutlineDraft(
        deck_title="Photosynthesis",
        slides=[
            _SlideDraft(title="Photosynthesis", bullets=[], source_refs=[]),
            _SlideDraft(
                title="Energy Conversion",
                bullets=["Light energy becomes chemical energy"],
                source_refs=[1],
            ),
            _SlideDraft(
                title="The Calvin Cycle",
                bullets=["Fixes CO2 into glucose"],
                source_refs=[2],
            ),
        ],
    )


async def _fake_marp(md_path: Path, out_path: Path, fmt: str) -> Path:
    """Stand-in for the Marp subprocess — writes a small placeholder file."""
    out_path.write_bytes(b"PK\x03\x04" + f"fake-{fmt}".encode())  # pptx/zip magic prefix
    return out_path


@pytest.mark.integration
async def test_integ_generate_slides_writes_ready_artifact(db_url: str) -> None:
    """generate_slides persists a ready artifact and uploads one file per format."""
    from asag.studio.slides import generate_slides

    ids = _Ids()
    storage = _FakeStorage()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        with (
            patch(
                "asag.studio.outline.structured_output",
                new=AsyncMock(return_value=_outline_draft()),
            ),
            patch("asag.studio.slides.marp_render", new=AsyncMock(side_effect=_fake_marp)),
        ):
            deck = await generate_slides(
                ids.notebook,
                pool=pool,
                storage=storage,
                n_slides=3,
                formats=("pptx", "html"),
            )

        # Returned deck.
        assert deck.title == "Photosynthesis"
        assert set(deck.file_urls) == {"pptx", "html"}
        assert deck.outline.slides[1].source_chunk_ids == [ids.chunk_a]
        assert deck.outline.slides[2].source_chunk_ids == [ids.chunk_b]

        # Storage received both formats with correct content types.
        assert len(storage.uploaded) == 2
        ctypes = {ct for _, ct in storage.uploaded.values()}
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in ctypes
        assert "text/html" in ctypes

        # DB artifact row is ready, points at the pptx, and stores the outline payload.
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT kind, status, title, file_url, payload FROM artifacts WHERE id = %s",
                (str(deck.artifact_id),),
            )
            row = await cur.fetchone()
        assert row is not None
        kind, status, title, file_url, payload = row
        assert kind == "slide_deck"
        assert status == "ready"
        assert title == "Photosynthesis"
        assert file_url == deck.file_urls["pptx"]
        assert len(payload["slides"]) == 3
    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_generate_slides_marks_failed_on_render_error(db_url: str) -> None:
    """A Marp failure marks the artifact ``failed`` and re-raises."""
    from asag.studio.slides import generate_slides

    ids = _Ids()
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        await _seed(db_url, ids)

        with (
            patch(
                "asag.studio.outline.structured_output",
                new=AsyncMock(return_value=_outline_draft()),
            ),
            patch(
                "asag.studio.slides.marp_render",
                new=AsyncMock(side_effect=RuntimeError("marp boom")),
            ),
            pytest.raises(RuntimeError, match="marp boom"),
        ):
            await generate_slides(
                ids.notebook, pool=pool, storage=_FakeStorage(), formats=("pptx",)
            )

        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            cur = await conn.execute(
                "SELECT status, error_message FROM artifacts WHERE notebook_id = %s",
                (str(ids.notebook),),
            )
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "failed"
        assert "marp boom" in (row[1] or "")
    finally:
        await _cleanup(db_url, ids)
        await pool.close()
