"""Abstract base class for all document loaders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from asag.models.ingestion import Element


class Loader(ABC):
    """Base class for all document loaders.

    Each loader converts a file on disk to a flat list of Elements.
    Chunking happens downstream (ingestion/chunkers/).

    All loaders are async — Docling is wrapped in asyncio.to_thread,
    LLM-based loaders (ImageLoader) use async LiteLLM calls directly.

    To add a new loader: subclass this, implement `parse`, then register in
    `ingestion/loaders/__init__.py` via `register("<type>", YourLoader)`.
    """

    @abstractmethod
    async def parse(self, file_path: Path) -> list[Element]:
        """Parse a file and return raw elements.

        Args:
            file_path: absolute path to the file on disk.

        Returns:
            Ordered list of Elements extracted from the file.
        """
