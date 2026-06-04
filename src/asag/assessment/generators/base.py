"""Shared helpers for question generators — numbered context + reference resolution.

Generators feed chunks to the LLM as a numbered list ([1], [2], ...) and ask the
model to cite by number. We then map those numbers back to real chunk UUIDs here,
so the model can never invent a chunk id (anti-hallucination grounding guarantee).
"""

from __future__ import annotations

import uuid

from asag.rag.retriever import ChunkResult


def numbered_context(chunks: list[ChunkResult]) -> tuple[str, dict[int, ChunkResult]]:
    """Format chunks as a numbered reference block; return text + ref→chunk map."""
    ref_map: dict[int, ChunkResult] = {}
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        ref_map[i] = chunk
        parts.append(f"[{i}] {chunk.content}")
    return "\n\n".join(parts), ref_map


def resolve_refs(refs: list[int], ref_map: dict[int, ChunkResult]) -> list[uuid.UUID]:
    """Map 1-based reference numbers to real chunk UUIDs, dropping out-of-range refs.

    Order is preserved and duplicates removed — a question may cite the same
    chunk number twice; we store each source chunk once.
    """
    seen: set[uuid.UUID] = set()
    result: list[uuid.UUID] = []
    for n in refs:
        chunk = ref_map.get(n)
        if chunk is not None and chunk.id not in seen:
            seen.add(chunk.id)
            result.append(chunk.id)
    return result
