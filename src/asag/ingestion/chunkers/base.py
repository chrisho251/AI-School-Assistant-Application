"""Abstract base class for all chunkers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import uuid

from asag.models.ingestion import Chunk, Element


class Chunker(ABC):
    """Base class for all chunkers.

    A chunker receives a list of Elements (from a loader) and returns
    an ordered list of Chunks ready for embedding and DB insertion.

    To add a new chunking strategy: subclass this, implement `chunk`,
    then register in `ingestion/chunkers/__init__.py`.
    """

    @abstractmethod
    def chunk(
        self,
        elements: list[Element],
        source_id: uuid.UUID,
        notebook_id: uuid.UUID,
    ) -> list[Chunk]:
        """Split elements into Chunks.

        Args:
            elements:    Ordered elements from the loader.
            source_id:   FK to the sources row.
            notebook_id: FK to the notebooks row (denormalized for fast filtering).

        Returns:
            Ordered Chunks with ordinal assigned starting from 0.
        """
