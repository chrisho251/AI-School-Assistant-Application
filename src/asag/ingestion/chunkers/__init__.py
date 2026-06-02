"""Chunker registry — maps strategy name to a Chunker class.

POC ships: semantic.
To add a new strategy: subclass Chunker, register here.
"""

from __future__ import annotations

from asag.ingestion.chunkers.base import Chunker
from asag.ingestion.chunkers.semantic import SemanticChunker

__all__ = ["Chunker", "SemanticChunker", "register", "get"]

_REGISTRY: dict[str, type[Chunker]] = {}


def register(name: str, cls: type[Chunker]) -> None:
    _REGISTRY[name] = cls


def get(name: str) -> Chunker:
    if name not in _REGISTRY:
        raise KeyError(f"No chunker registered for {name!r}. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]()


# ---- Register built-in chunkers ----
register("semantic", SemanticChunker)
