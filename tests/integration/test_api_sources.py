"""Integration test — PDF upload + background ingestion through the API.

Full-stack: needs Supabase Storage + TEI embeddings + Docling, so it is gated behind
``ASAG_TEST_FULL_STACK=1`` to stay out of the default suite. With the stack up, it
uploads a real PDF and polls the source status until ingestion reaches ``ready``.

PowerShell:  $env:ASAG_TEST_FULL_STACK='1'; uv run pytest -m integration tests/integration/test_api_sources.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
import uuid

from httpx import AsyncClient
import psycopg
import pytest

from asag.api.deps import get_storage
from asag.api.main import app
from tests.integration.conftest import auth_header

pytestmark = pytest.mark.integration

_SAMPLE_PDF = Path(r"E:\study\ASAG-sample\sample-pdf\diagnostics-14-01182-v2.pdf")


class _FakeStorage:
    """In-memory storage stub so the upload path needs no Supabase."""

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        return f"memory://{key}"

    async def download(self, key: str) -> bytes:  # pragma: no cover
        return b""

    async def delete(self, key: str) -> None:  # pragma: no cover
        return None

    async def get_public_url(self, key: str) -> str:  # pragma: no cover
        return f"memory://{key}"


async def test_integ_api_upload_commits_source_row(
    api: AsyncClient, db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the source row must be durably committed before ingestion runs.

    Mocks storage + the ingest task (no TEI/Docling) and asserts the row exists in
    the DB afterwards — this fails if the background task's exception rolls back the
    request transaction (the bug found during manual Day 9 testing).
    """
    org, teacher, klass, notebook = (uuid.uuid4() for _ in range(4))
    ingested: list[uuid.UUID] = []

    async def fake_ingest(source_id: uuid.UUID, **kw: Any) -> None:
        ingested.append(source_id)

    monkeypatch.setattr("asag.api.routers.sources.ingest_source", fake_ingest)
    app.dependency_overrides[get_storage] = lambda: _FakeStorage()

    async def seed() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s)",
                (org, "Org", f"org-{org.hex[:8]}"),
            )
            await c.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) "
                "VALUES (%s,%s,%s,%s,'teacher')",
                (teacher, org, f"{teacher}@x.com", "T"),
            )
            await c.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
                (klass, org, "C", teacher),
            )
            await c.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
                (notebook, klass, teacher, "NB"),
            )
            await c.commit()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute("DELETE FROM notebooks WHERE id = %s", (notebook,))
            await c.execute("DELETE FROM classes WHERE id = %s", (klass,))
            await c.execute("DELETE FROM users WHERE id = %s", (teacher,))
            await c.execute("DELETE FROM organizations WHERE id = %s", (org,))
            await c.commit()

    await seed()
    try:
        hdr = auth_header(teacher, org, "teacher")
        files = {"file": ("doc.pdf", b"%PDF-1.4 fake bytes", "application/pdf")}
        resp = await api.post(
            "/sources", data={"notebook_id": str(notebook)}, files=files, headers=hdr
        )
        assert resp.status_code == 202, resp.text
        source_id = resp.json()["id"]
        assert ingested == [uuid.UUID(source_id)]  # background task fired

        # The row must survive in the DB (superuser view bypasses RLS).
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            cur = await c.execute("SELECT count(*) FROM sources WHERE id = %s", (source_id,))
            count = (await cur.fetchone())[0]  # type: ignore[index]
        assert count == 1, "source row was rolled back — background task ordering bug"
    finally:
        await cleanup()


@pytest.mark.skipif(
    not os.getenv("ASAG_TEST_FULL_STACK"), reason="set ASAG_TEST_FULL_STACK=1 (needs storage + TEI)"
)
async def test_integ_api_upload_and_ingest(api: AsyncClient, db_url: str) -> None:
    if not _SAMPLE_PDF.exists():
        pytest.skip(f"sample PDF not found at {_SAMPLE_PDF}")

    org = uuid.uuid4()
    teacher = uuid.uuid4()
    klass = uuid.uuid4()
    notebook = uuid.uuid4()

    async def seed() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s,%s,%s)",
                (org, "Org", f"org-{org.hex[:8]}"),
            )
            await c.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) "
                "VALUES (%s,%s,%s,%s,'teacher')",
                (teacher, org, f"{teacher}@x.com", "T"),
            )
            await c.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s,%s,%s,%s)",
                (klass, org, "C", teacher),
            )
            await c.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s,%s,%s,%s)",
                (notebook, klass, teacher, "NB"),
            )
            await c.commit()

    async def cleanup() -> None:
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            await c.execute(
                "DELETE FROM notebooks WHERE id = %s", (notebook,)
            )  # cascades sources/chunks
            await c.execute("DELETE FROM classes WHERE id = %s", (klass,))
            await c.execute("DELETE FROM users WHERE id = %s", (teacher,))
            await c.execute("DELETE FROM organizations WHERE id = %s", (org,))
            await c.commit()

    await seed()
    try:
        hdr = auth_header(teacher, org, "teacher")
        files = {"file": (_SAMPLE_PDF.name, _SAMPLE_PDF.read_bytes(), "application/pdf")}
        resp = await api.post(
            "/sources", data={"notebook_id": str(notebook)}, files=files, headers=hdr
        )
        assert resp.status_code == 202, resp.text
        source_id = resp.json()["id"]
        assert resp.json()["ingestion_status"] == "pending"

        # Poll until the background pipeline finishes (Docling + embeddings are slow).
        final_status = "pending"
        for _ in range(60):
            await asyncio.sleep(2)
            rows = (await api.get(f"/sources/notebook/{notebook}", headers=hdr)).json()
            match = next((r for r in rows if r["id"] == source_id), None)
            assert match is not None
            final_status = match["ingestion_status"]
            if final_status in ("ready", "failed"):
                break
        assert final_status == "ready", f"ingestion ended in {final_status!r}"

        # Chunks should exist for the source.
        async with await psycopg.AsyncConnection.connect(db_url) as c:
            cur = await c.execute("SELECT count(*) FROM chunks WHERE source_id = %s", (source_id,))
            count = (await cur.fetchone())[0]  # type: ignore[index]
        assert count > 0
    finally:
        await cleanup()
