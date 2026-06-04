"""Source upload + ingestion trigger, and per-notebook source listing.

``POST /sources`` stores the file, writes a ``sources`` row under RLS (which also
authorizes that the caller owns the notebook), then defers the heavy ingestion
pipeline to a background task that runs as the service role.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from psycopg_pool import AsyncConnectionPool

from asag.api.deps import (
    AuthContext,
    get_db,
    get_pool,
    get_storage,
    require_teacher,
    rls_connection,
    verify_jwt,
)
from asag.core.queue import BackgroundTaskQueue
from asag.core.storage import StorageBackend
from asag.ingestion.pipeline import ingest_source
from asag.ingestion.repository import NotebookRepository, SourceRepository
from asag.models.api import SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])

# Filename suffix → loader registry key. Extension hook: register more here as
# loaders are added (docx, code, notebook).
_SUFFIX_TO_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}

_CONTENT_TYPE = {"pdf": "application/pdf", "image": "application/octet-stream"}


@router.post("", response_model=SourceOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_source(
    background_tasks: BackgroundTasks,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_teacher),
    pool: AsyncConnectionPool = Depends(get_pool),
    storage: StorageBackend = Depends(get_storage),
) -> SourceOut:
    """Upload a PDF/image, persist the source row, and queue ingestion.

    Returns 202 with the source in ``pending`` status; clients poll
    ``GET /sources/notebook/{id}`` for the status to reach ``ready``.

    The RLS transaction is opened and committed *inline* (not via ``get_db``) so the
    source row is durable before ``ingest_source`` runs — otherwise the background
    task could not see the still-uncommitted row, and its failure would roll the
    insert back through the dependency exit stack.
    """
    suffix = Path(file.filename or "").suffix.lower()
    source_type = _SUFFIX_TO_TYPE.get(suffix)
    if source_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type {suffix!r}; allowed: {sorted(_SUFFIX_TO_TYPE)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    checksum = hashlib.sha256(data).hexdigest()

    async with rls_connection(pool, auth) as conn:
        # Authorize BEFORE writing to storage: under RLS a non-owner sees no notebook,
        # so this also stops a teacher from dumping objects into another notebook's
        # storage namespace.
        notebook = await NotebookRepository(conn).get_by_id(notebook_id)
        if notebook is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
        if uuid.UUID(str(notebook["owner_id"])) != auth.user_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only the notebook owner can add sources"
            )

        # Storage key namespaced by notebook + content hash → idempotent re-uploads.
        storage_key = f"{notebook_id}/{checksum}{suffix}"
        await storage.upload(storage_key, data, _CONTENT_TYPE[source_type])

        try:
            row = await SourceRepository(conn).create(
                notebook_id=notebook_id,
                source_type=source_type,
                original_filename=file.filename or f"upload{suffix}",
                storage_url=storage_key,
                checksum=checksum,
                file_size_bytes=len(data),
            )
        except UniqueViolation as exc:  # (notebook_id, checksum) already ingested
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This file was already added to the notebook"
            ) from exc

    # Transaction committed above; ingestion runs as the service role after the response.
    BackgroundTaskQueue(background_tasks).enqueue(
        ingest_source, uuid.UUID(str(row["id"])), pool=pool, storage=storage
    )

    return SourceOut(**row)


@router.get("/notebook/{notebook_id}", response_model=list[SourceOut])
async def list_sources(
    notebook_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> list[SourceOut]:
    """List a notebook's sources with ingestion status (RLS-filtered)."""
    repo = SourceRepository(db)
    rows = await repo.list_by_notebook(notebook_id)
    return [SourceOut(**r) for r in rows]
