"""Storage backend — abstract interface + SupabaseStorage implementation.

To add a new storage backend (e.g. R2):
    1. Subclass `StorageBackend` and implement the four abstract methods.
    2. Add it to the factory in `get_storage_backend()`.
    3. Flip `STORAGE_BACKEND=r2` in .env.

POC uses Supabase Storage. R2 backend is a future extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import logging

log = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract interface for object storage operations."""

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload *data* under *key* and return the public URL."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Return the raw bytes stored at *key*."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object at *key* (no-op if missing)."""

    @abstractmethod
    async def get_public_url(self, key: str) -> str:
        """Return the public URL for *key* without downloading."""


class SupabaseStorage(StorageBackend):
    """Supabase Storage backend using the official supabase-py client.

    All calls wrap the synchronous supabase-py API via `asyncio.to_thread`
    so the interface stays async without pulling in the heavier async client.

    Args:
        url:         Supabase project URL (SUPABASE_URL).
        service_key: service_role key — required for server-side uploads.
        bucket:      Storage bucket name (default "asag-sources").
    """

    def __init__(self, url: str, service_key: str, bucket: str = "asag-sources") -> None:
        from supabase import create_client  # lazy — avoid import overhead at module level

        self._bucket = bucket
        self._client = create_client(url, service_key)
        log.debug("SupabaseStorage ready: bucket=%s", bucket)

    # ------------------------------------------------------------------ #
    # StorageBackend interface                                             #
    # ------------------------------------------------------------------ #

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload *data* and return its public URL.

        Uses upsert=True so re-uploading the same key is idempotent.
        """
        storage = self._client.storage.from_(self._bucket)

        def _do_upload() -> None:
            storage.upload(
                path=key,
                file=data,
                file_options={"content-type": content_type, "x-upsert": "true"},
            )

        await asyncio.to_thread(_do_upload)
        log.debug("Uploaded %s (%d bytes)", key, len(data))
        return await self.get_public_url(key)

    async def download(self, key: str) -> bytes:
        storage = self._client.storage.from_(self._bucket)
        result: bytes = await asyncio.to_thread(storage.download, key)
        return result

    async def delete(self, key: str) -> None:
        storage = self._client.storage.from_(self._bucket)
        await asyncio.to_thread(storage.remove, [key])
        log.debug("Deleted %s", key)

    async def get_public_url(self, key: str) -> str:
        storage = self._client.storage.from_(self._bucket)
        # get_public_url is synchronous and CPU-bound (just string formatting)
        return storage.get_public_url(key)


def get_storage_backend() -> StorageBackend:
    """Factory — returns the configured storage backend.

    Reads `STORAGE_BACKEND` from settings.  Currently only `supabase` is
    implemented; extend here when R2 backend ships.
    """
    from asag.config import get_settings

    cfg = get_settings()
    if cfg.storage_backend == "supabase":
        return SupabaseStorage(
            url=cfg.supabase_url,
            service_key=cfg.supabase_service_key,
            bucket="asag-sources",
        )
    raise ValueError(f"Unknown STORAGE_BACKEND={cfg.storage_backend!r}. Valid: supabase")
