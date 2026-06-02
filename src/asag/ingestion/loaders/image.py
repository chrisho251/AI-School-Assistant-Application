"""Image loader — calls Gemini Vision to produce an academic caption.

Handles standalone PNG/JPG uploads only.
Embedded images inside PDFs are NOT extracted here (out of scope for POC).

The caption becomes the searchable text for this chunk; the original
storage URL is added to metadata by the pipeline after parse() returns.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from asag.core.llm import chat
from asag.ingestion.loaders.base import Loader
from asag.models.ingestion import ContentType, Element

log = logging.getLogger(__name__)

# MIME types this loader handles
_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Load prompt once at module import — it's a constant, not dynamic
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "image_caption.md"
_CAPTION_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")


class ImageLoader(Loader):
    """Convert a standalone image file to a single image_caption Element.

    Calls Gemini Vision (via LiteLLM) with a strict academic captioning prompt.
    The resulting caption text is what gets embedded and indexed for retrieval;
    the original image URL is kept in metadata so the UI can render the image
    alongside retrieved chunks.

    Args:
        model: LiteLLM model string. Defaults to ``ASAG_LLM_GENERATOR`` from
               settings (Gemini 2.5 Flash).
    """

    def __init__(self, model: str | None = None) -> None:
        from asag.config import get_settings

        cfg = get_settings()
        self._model = model or cfg.asag_llm_generator

    async def parse(self, file_path: Path) -> list[Element]:
        """Call Gemini Vision and return a single image_caption Element."""
        mime = self._mime_type(file_path)
        # File read is small (images for captioning); wrap in to_thread to comply
        # with async-I/O-everywhere rule.
        image_bytes = await asyncio.to_thread(file_path.read_bytes)

        log.info(
            "ImageLoader: captioning %s (%d bytes) via %s",
            file_path.name,
            len(image_bytes),
            self._model,
        )

        caption = await chat(
            messages=[{"role": "user", "content": _CAPTION_PROMPT}],
            model=self._model,
            images=[(image_bytes, mime)],
        )

        caption = caption.strip()
        log.info("ImageLoader: caption length=%d chars", len(caption))

        return [
            Element(
                content=caption,
                content_type=ContentType.image_caption,
                page_number=None,
                # original_image_url is injected by the pipeline after upload
                metadata={"original_filename": file_path.name, "mime_type": mime},
            )
        ]

    @staticmethod
    def _mime_type(file_path: Path) -> str:
        mime = _MIME_MAP.get(file_path.suffix.lower())
        if mime is None:
            raise ValueError(
                f"Unsupported image extension {file_path.suffix!r}. Supported: {list(_MIME_MAP)}"
            )
        return mime
