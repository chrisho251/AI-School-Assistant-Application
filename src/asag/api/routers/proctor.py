"""Proctor events — record browser-lockdown violations during an exam attempt.

The student's lockdown component POSTs one event per violation (tab switch, blur,
fullscreen exit, blocked key); the teacher review screen GETs the timeline. Both run
under RLS: a student touches only their own in-progress attempt, the quiz creator can
read every attempt's events.
"""

from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection

from asag.api.deps import AuthContext, get_db, verify_jwt
from asag.assessment.repository import AssessmentApiRepository
from asag.models.api import ProctorEvent

router = APIRouter(prefix="/attempts", tags=["proctor"])


@router.post("/{attempt_id}/proctor_event", status_code=status.HTTP_204_NO_CONTENT)
async def record_proctor_event(
    attempt_id: uuid.UUID,
    body: ProctorEvent,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> None:
    """Append a lockdown event to the caller's in-progress attempt."""
    repo = AssessmentApiRepository(db)
    attempt = await repo.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    if uuid.UUID(str(attempt["student_id"])) != auth.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your attempt")
    # Events are only meaningful during the exam; once submitted the proctor log is
    # closed so a student cannot pad it after the fact.
    if attempt["status"] != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Attempt is no longer in progress")
    await repo.append_proctor_event(attempt_id, body.event_type, body.payload)


@router.get("/{attempt_id}/proctor_events")
async def list_proctor_events(
    attempt_id: uuid.UUID,
    auth: AuthContext = Depends(verify_jwt),
    db: AsyncConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return an attempt's proctor timeline for the teacher review screen.

    RLS limits visibility to the owning student or the quiz creator, so no extra
    role check is needed here — a 404 surfaces if the caller cannot see the attempt.
    """
    repo = AssessmentApiRepository(db)
    if await repo.get_attempt(attempt_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return await repo.get_proctor_events(attempt_id)
