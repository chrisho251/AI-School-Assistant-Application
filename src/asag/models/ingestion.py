"""Pydantic models for ingestion pipeline — Element and Chunk."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class ContentType(StrEnum):
    """Canonical content types for chunks stored in the DB."""

    text = "text"
    table = "table"
    image_caption = "image_caption"
    code = "code"


class Element(BaseModel):
    """Raw parsed unit from a loader — before chunking or embedding.

    Produced by loaders (PdfLoader, ImageLoader, etc.) and consumed by chunkers.
    """

    content: str
    content_type: ContentType = ContentType.text
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResult(BaseModel):
    """Returned by ingest_source() after pipeline completes."""

    source_id: uuid.UUID
    chunks_written: int
    status: str  # "ready" | "failed" | "skipped"


class Chunk(BaseModel):
    """Semantic unit ready for storage in the `chunks` table.

    Produced by chunkers after splitting Element content.
    Embedding fields are filled by the embedding stage (Session 3A).
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: uuid.UUID
    notebook_id: uuid.UUID
    ordinal: int
    content: str
    content_type: ContentType = ContentType.text
    page_number: int | None = None
    embedding: list[float] | None = None  # BGE-M3 dense vector (1024d)
    sparse_vector: dict[str, float] | None = None  # BM25/SPLADE weights
    metadata: dict[str, Any] = Field(default_factory=dict)
