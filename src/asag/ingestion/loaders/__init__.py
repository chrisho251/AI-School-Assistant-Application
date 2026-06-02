"""Loader registry — maps MIME type / source_type string to a Loader class.

To add a new loader:
    1. Implement a class that extends `Loader` in a sibling module.
    2. Call `register("<type>", YourLoader)` at the bottom of this file.
    3. Add the MIME → type mapping to `_MIME_MAP` if applicable.

POC ships: pdf, image (image registered in Session 2C).
"""

from __future__ import annotations

from asag.ingestion.loaders.base import Loader
from asag.ingestion.loaders.image import ImageLoader
from asag.ingestion.loaders.pdf import PdfLoader

__all__ = ["Loader", "ImageLoader", "PdfLoader", "register", "get", "get_for_mime"]

# source_type string → Loader subclass
_REGISTRY: dict[str, type[Loader]] = {}

# MIME type → source_type string (for routing uploaded files)
_MIME_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    # "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def register(name: str, cls: type[Loader]) -> None:
    """Register a loader under *name* (e.g. "pdf", "image")."""
    _REGISTRY[name] = cls


def get(name: str) -> Loader:
    """Return a fresh Loader instance for *name*.

    Raises:
        KeyError: if no loader is registered for *name*.
    """
    if name not in _REGISTRY:
        raise KeyError(f"No loader registered for {name!r}. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]()


def get_for_mime(mime_type: str) -> Loader:
    """Return a loader for the given MIME type.

    Raises:
        KeyError: if no mapping exists for *mime_type*.
    """
    source_type = _MIME_MAP.get(mime_type)
    if source_type is None:
        raise KeyError(f"No loader for MIME type {mime_type!r}. Supported: {list(_MIME_MAP)}")
    return get(source_type)


# ---- Register built-in loaders ----
register("pdf", PdfLoader)
register("image", ImageLoader)
