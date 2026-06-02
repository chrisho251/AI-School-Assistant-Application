"""Semantic chunker — token-aware, heading-boundary-respecting.

Strategy:
  - Target ~1 000 tokens per chunk, overlap ~150 tokens.
  - Heading elements (title, section_header) trigger a chunk boundary.
  - Table elements are atomic — always emitted as their own chunk.
  - Overlap: tail elements from the previous window are prepended to the
    next window so retrieval has cross-boundary context.

Token counting uses cl100k_base (tiktoken) as a cheap proxy for BGE-M3's
tokenizer — the target is rough; exact count doesn't matter for chunking.
"""

from __future__ import annotations

from functools import cached_property
import uuid

import tiktoken

from asag.ingestion.chunkers.base import Chunker
from asag.models.ingestion import Chunk, ContentType, Element

# Docling label strings that signal a section boundary
_HEADING_LABELS: frozenset[str] = frozenset(
    {"title", "section_header", "section-header", "page_header"}
)


class SemanticChunker(Chunker):
    """Sliding-window chunker with heading-aware boundary detection.

    Args:
        max_tokens:     Target token ceiling per chunk (default 1 000).
        overlap_tokens: Tokens from the previous chunk carried into the
                        next chunk for retrieval context (default 150).
    """

    def __init__(self, max_tokens: int = 1000, overlap_tokens: int = 150) -> None:
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def chunk(
        self,
        elements: list[Element],
        source_id: uuid.UUID,
        notebook_id: uuid.UUID,
    ) -> list[Chunk]:
        result: list[Chunk] = []
        window: list[Element] = []
        has_new = False  # tracks whether window has content beyond overlap

        def flush(reset_overlap: bool = False) -> None:
            nonlocal window, has_new
            if not window:
                return
            result.append(self._make_chunk(window, source_id, notebook_id, len(result)))
            window = [] if reset_overlap else self._overlap(window)
            has_new = False

        for element in elements:
            # Tables are atomic — flush current window, emit table standalone
            if element.content_type == ContentType.table:
                if has_new:
                    flush()
                result.append(self._make_chunk([element], source_id, notebook_id, len(result)))
                window = []  # no overlap after a table
                has_new = False
                continue

            # Headings mark section boundaries — flush before starting new section
            if self._is_heading(element) and has_new:
                flush()

            window.append(element)
            has_new = True

            if self._window_tokens(window) >= self.max_tokens:
                flush()

        if has_new:
            flush(reset_overlap=True)

        return result

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @cached_property
    def _enc(self) -> tiktoken.Encoding:
        return tiktoken.get_encoding("cl100k_base")

    def _count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def _window_tokens(self, window: list[Element]) -> int:
        return sum(self._count(e.content) for e in window)

    def _overlap(self, window: list[Element]) -> list[Element]:
        """Return the tail of *window* that fits within overlap_tokens."""
        carry: list[Element] = []
        tokens = 0
        for e in reversed(window):
            t = self._count(e.content)
            if tokens + t > self.overlap_tokens:
                break
            carry.insert(0, e)
            tokens += t
        return carry

    @staticmethod
    def _is_heading(element: Element) -> bool:
        return element.metadata.get("label", "") in _HEADING_LABELS

    @staticmethod
    def _make_chunk(
        window: list[Element],
        source_id: uuid.UUID,
        notebook_id: uuid.UUID,
        ordinal: int,
    ) -> Chunk:
        content = "\n\n".join(e.content for e in window)
        # Single-element window inherits its content_type; multi-element → text
        content_type = window[0].content_type if len(window) == 1 else ContentType.text
        return Chunk(
            source_id=source_id,
            notebook_id=notebook_id,
            ordinal=ordinal,
            content=content,
            content_type=content_type,
            page_number=window[0].page_number,
            metadata={"element_count": len(window)},
        )
