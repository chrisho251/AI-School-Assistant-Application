"""PDF loader — wraps Docling DocumentConverter.

Extracts text and table elements preserving page numbers.
Docling is CPU-bound and blocking; it runs in a thread pool via
asyncio.to_thread so the event loop is never blocked.
Embedded images in PDFs are skipped (standalone image upload handled
by ImageLoader in 2C).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
import logging
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter

from asag.ingestion.loaders.base import Loader
from asag.models.ingestion import ContentType, Element

log = logging.getLogger(__name__)


class PdfLoader(Loader):
    """Convert a PDF file to a list of Elements via Docling.

    Docling handles text extraction, table detection, and layout analysis.
    Each element carries its page number for citation purposes.
    """

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    async def parse(self, file_path: Path) -> list[Element]:
        """Parse *file_path* and return extracted Elements.

        Runs Docling in a thread pool so the async event loop stays free.
        """
        return await asyncio.to_thread(self._sync_parse, file_path)

    # ------------------------------------------------------------------ #
    # Sync implementation (thread-pool target)                            #
    # ------------------------------------------------------------------ #

    def _sync_parse(self, file_path: Path) -> list[Element]:
        """Blocking Docling parse — called via asyncio.to_thread."""
        log.info("PDF loader: converting %s", file_path.name)
        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        elements = list(self._extract_elements(result.document))
        log.info("PDF loader: extracted %d elements from %s", len(elements), file_path.name)
        return elements

    # ------------------------------------------------------------------ #
    # Internal helpers (duck-typed so mock objects work in unit tests)    #
    # ------------------------------------------------------------------ #

    def _extract_elements(self, doc: Any) -> Iterator[Element]:
        """Yield Elements from a Docling DoclingDocument."""
        for item, _level in doc.iterate_items():
            if self._is_table(item):
                yield from self._table_element(item)
            elif self._is_text(item):
                yield from self._text_element(item)
            # figures / other types: skip for POC

    @staticmethod
    def _is_table(item: Any) -> bool:
        return callable(getattr(item, "export_to_markdown", None))

    @staticmethod
    def _is_text(item: Any) -> bool:
        text = getattr(item, "text", None)
        return isinstance(text, str) and bool(text.strip())

    @staticmethod
    def _page_number(item: Any) -> int | None:
        prov = getattr(item, "prov", None)
        if prov:
            return getattr(prov[0], "page_no", None)
        return None

    def _table_element(self, item: Any) -> Iterator[Element]:
        md = item.export_to_markdown()
        if md.strip():
            yield Element(
                content=md,
                content_type=ContentType.table,
                page_number=self._page_number(item),
                metadata={"label": "table"},
            )

    def _text_element(self, item: Any) -> Iterator[Element]:
        text = item.text.strip()
        label = str(getattr(item, "label", "text"))
        yield Element(
            content=text,
            content_type=ContentType.text,
            page_number=self._page_number(item),
            metadata={"label": label},
        )
