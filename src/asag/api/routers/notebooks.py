"""Notebook CRUD — create, list, get. All access is RLS-filtered via ``get_db``."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection

from asag.api.deps import AuthContext, get_db, require_teacher, verify_jwt
from asag.ingestion.repository import NotebookRepository
from asag.models.api import NotebookCreate, NotebookOut

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.post("", response_model=NotebookOut, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    body: NotebookCreate,
    auth: AuthContext = Depends(require_teacher),
    db: AsyncConnection = Depends(get_db),
) -> NotebookOut:
    """Create a notebook owned by the calling teacher.

    RLS rejects the insert if ``owner_id`` is not the caller, so ownership cannot
    be spoofed even though the route also sets it explicitly.
    """
    repo = NotebookRepository(db)
    # The notebooks RLS insert policy only checks owner_id; guard here that the
    # class is in the caller's org and taught by them, so a notebook cannot be
    # attached to (and leaked into) another tenant's class.
    teacher_id = await repo.get_class_teacher(body.class_id)
    if teacher_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Class not found")
    if teacher_id != auth.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    row = await repo.create(
        class_id=body.class_id,
        owner_id=auth.user_id,
        title=body.title,
        subject=body.subject,
        description=body.description,
    )
    return NotebookOut(**row)


@router.get("", response_model=list[NotebookOut])
async def list_notebooks(
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> list[NotebookOut]:
    """List notebooks the caller can see (own, ACL-granted, or class membership)."""
    repo = NotebookRepository(db)
    rows = await repo.list_for_user()
    return [NotebookOut(**r) for r in rows]


@router.get("/{notebook_id}", response_model=NotebookOut)
async def get_notebook(
    notebook_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> NotebookOut:
    """Fetch one notebook; 404 if it does not exist or the caller lacks access."""
    repo = NotebookRepository(db)
    row = await repo.get_by_id(notebook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
    return NotebookOut(**row)
