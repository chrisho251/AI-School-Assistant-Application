"""Integration test: ingestion pipeline writes chunks to Postgres.

The loader is mocked so no real PDF or Docling model download is needed.
This tests: DB connectivity, repository pattern, source status updates,
chunk bulk-insert, and idempotency.

Run from home / with Supabase reachable:
    uv run pytest tests/integration/test_ingestion_e2e.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.ingestion.pipeline import ingest_source
from asag.models.ingestion import ContentType, Element, IngestResult

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
def mock_storage() -> MagicMock:
    """Fake storage backend — all async methods stubbed."""
    storage = MagicMock()
    storage.download = AsyncMock(return_value=b"%PDF-1.4 fake content")
    storage.upload = AsyncMock(return_value="http://fake/url")
    storage.get_public_url = AsyncMock(return_value="http://fake/public/url")
    return storage


@pytest.fixture
def sample_elements() -> list[Element]:
    return [
        Element(
            content="Introduction to machine learning.",
            content_type=ContentType.text,
            page_number=1,
            metadata={"label": "text"},
        ),
        Element(
            content="Supervised learning is a type of ML.",
            content_type=ContentType.text,
            page_number=1,
            metadata={"label": "text"},
        ),
        Element(
            content="| Algo | Accuracy |\n|---|---|\n| SVM | 92% |",
            content_type=ContentType.table,
            page_number=2,
            metadata={"label": "table"},
        ),
        Element(
            content="Conclusion: choose the right algorithm.",
            content_type=ContentType.text,
            page_number=3,
            metadata={"label": "text"},
        ),
    ]


async def _cleanup(db_url: str, ids: dict[str, uuid.UUID]) -> None:
    """Delete test rows using a fresh superuser connection (bypasses RLS)."""
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        await conn.execute("DELETE FROM chunks       WHERE source_id  = %s", (str(ids["source"]),))
        await conn.execute("DELETE FROM sources      WHERE id         = %s", (str(ids["source"]),))
        await conn.execute(
            "DELETE FROM notebooks    WHERE id         = %s", (str(ids["notebook"]),)
        )
        await conn.execute("DELETE FROM classes      WHERE id         = %s", (str(ids["class_"]),))
        await conn.execute("DELETE FROM users        WHERE id         = %s", (str(ids["user"]),))
        await conn.execute("DELETE FROM organizations WHERE id        = %s", (str(ids["org"]),))
        await conn.commit()


@pytest.mark.integration
async def test_integ_ingest_source_writes_chunks(
    db_url: str, mock_storage, sample_elements
) -> None:
    """Pipeline writes correct number of chunks and sets status=ready."""
    ids: dict[str, uuid.UUID] = {
        "org": uuid.uuid4(),
        "user": uuid.uuid4(),
        "class_": uuid.uuid4(),
        "notebook": uuid.uuid4(),
        "source": uuid.uuid4(),
    }

    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        # ---- Seed test data ----
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (str(ids["org"]), "Test Org E2E", f"test-e2e-{ids['org'].hex[:8]}"),
            )
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
                (str(ids["user"]), str(ids["org"]), "e2e@test.com", "E2E Teacher", "teacher"),
            )
            await conn.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
                (str(ids["class_"]), str(ids["org"]), "E2E Class", str(ids["user"])),
            )
            await conn.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
                (str(ids["notebook"]), str(ids["class_"]), str(ids["user"]), "E2E Notebook"),
            )
            await conn.execute(
                """INSERT INTO sources
                   (id, notebook_id, source_type, original_filename, storage_url, ingestion_status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    str(ids["source"]),
                    str(ids["notebook"]),
                    "pdf",
                    "sample.pdf",
                    "test/sample.pdf",
                    "pending",
                ),
            )
            await conn.commit()

        # ---- Run pipeline with mocked loader ----
        with patch("asag.ingestion.pipeline.loader_registry.get") as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.parse = AsyncMock(return_value=sample_elements)
            mock_get_loader.return_value = mock_loader

            result: IngestResult = await ingest_source(
                ids["source"],
                pool=pool,
                storage=mock_storage,
            )

        # ---- Assertions ----
        assert result.status == "ready"
        assert result.source_id == ids["source"]
        assert result.chunks_written > 0

        # Verify rows in DB
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM chunks WHERE source_id = %s",
                (str(ids["source"]),),
            )
            row = await cur.fetchone()
            assert row is not None and row[0] == result.chunks_written

            # Source status must be "ready"
            await cur.execute(
                "SELECT ingestion_status FROM sources WHERE id = %s",
                (str(ids["source"]),),
            )
            status_row = await cur.fetchone()
            assert status_row is not None and status_row[0] == "ready"

    finally:
        await _cleanup(db_url, ids)
        await pool.close()


@pytest.mark.integration
async def test_integ_ingest_source_idempotent(db_url: str, mock_storage, sample_elements) -> None:
    """Re-running on a 'ready' source returns status='skipped' without touching chunks."""
    ids: dict[str, uuid.UUID] = {
        "org": uuid.uuid4(),
        "user": uuid.uuid4(),
        "class_": uuid.uuid4(),
        "notebook": uuid.uuid4(),
        "source": uuid.uuid4(),
    }

    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (str(ids["org"]), "Idempotency Org", f"idempotent-{ids['org'].hex[:8]}"),
            )
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
                (str(ids["user"]), str(ids["org"]), "idp@test.com", "Teacher", "teacher"),
            )
            await conn.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
                (str(ids["class_"]), str(ids["org"]), "Class", str(ids["user"])),
            )
            await conn.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
                (str(ids["notebook"]), str(ids["class_"]), str(ids["user"]), "Notebook"),
            )
            # Source already "ready"
            await conn.execute(
                """INSERT INTO sources
                   (id, notebook_id, source_type, original_filename, storage_url, ingestion_status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    str(ids["source"]),
                    str(ids["notebook"]),
                    "pdf",
                    "sample.pdf",
                    "test/sample.pdf",
                    "ready",
                ),
            )
            await conn.commit()

        result = await ingest_source(ids["source"], pool=pool, storage=mock_storage)

        assert result.status == "skipped"
        assert result.chunks_written == 0
        mock_storage.download.assert_not_called()

    finally:
        await _cleanup(db_url, ids)
        await pool.close()
