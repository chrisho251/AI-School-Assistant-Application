"""Pydantic models for RAG Q&A results."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Reference to a specific chunk that supported an answer."""

    source_id: uuid.UUID
    chunk_id: uuid.UUID
    page_number: int | None = None


class AnswerResult(BaseModel):
    """Result of a single Q&A turn including the answer, citations, and DB IDs."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    tokens_used: int | None = None
