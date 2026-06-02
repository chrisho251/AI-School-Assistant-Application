"""Unit tests for ImageLoader — LLM call is mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from asag.ingestion.loaders import get, get_for_mime
from asag.ingestion.loaders.image import ImageLoader
from asag.models.ingestion import ContentType

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

_FAKE_CAPTION = (
    "The bar chart displays quarterly revenue for four product lines "
    "from 2022 to 2024, with the y-axis representing millions of USD. "
    "Product A shows the highest growth, reaching 45M in Q4 2024."
)

_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    p = tmp_path / "chart.png"
    p.write_bytes(_MINIMAL_PNG)
    return p


@pytest.fixture
def jpg_file(tmp_path: Path) -> Path:
    p = tmp_path / "slide.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 50 + b"\xff\xd9")
    return p


# ------------------------------------------------------------------ #
# ImageLoader.parse() tests (async)                                    #
# ------------------------------------------------------------------ #


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_png_returns_single_element(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader(model="gemini/gemini-2.5-flash")
    elements = await loader.parse(png_file)

    assert len(elements) == 1
    assert mock_chat.called


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_content_type_is_image_caption(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].content_type == ContentType.image_caption


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_content_is_stripped_caption(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].content == _FAKE_CAPTION.strip()


@patch(
    "asag.ingestion.loaders.image.chat",
    new_callable=AsyncMock,
    return_value="  caption with whitespace  ",
)
async def test_parse_strips_whitespace(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].content == "caption with whitespace"


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_metadata_has_filename(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].metadata["original_filename"] == "chart.png"


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_metadata_has_mime_type(mock_chat: AsyncMock, png_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].metadata["mime_type"] == "image/png"


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_page_number_is_none(mock_chat: AsyncMock, png_file: Path) -> None:
    """Images have no page number — page_number must be None."""
    loader = ImageLoader()
    elements = await loader.parse(png_file)

    assert elements[0].page_number is None


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_passes_image_bytes_to_llm(mock_chat: AsyncMock, png_file: Path) -> None:
    """Loader must pass the image bytes in the `images` kwarg."""
    loader = ImageLoader()
    await loader.parse(png_file)

    _, kwargs = mock_chat.call_args
    images = kwargs.get("images")
    assert images is not None and len(images) == 1
    raw_bytes, mime = images[0]
    assert raw_bytes == _MINIMAL_PNG
    assert mime == "image/png"


@patch("asag.ingestion.loaders.image.chat", new_callable=AsyncMock, return_value=_FAKE_CAPTION)
async def test_parse_jpeg_extension(mock_chat: AsyncMock, jpg_file: Path) -> None:
    loader = ImageLoader()
    elements = await loader.parse(jpg_file)

    assert elements[0].metadata["mime_type"] == "image/jpeg"


async def test_parse_unsupported_extension_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "document.bmp"
    bad_file.write_bytes(b"BM fake bmp")
    loader = ImageLoader()

    with pytest.raises(ValueError, match="Unsupported image extension"):
        await loader.parse(bad_file)


# ------------------------------------------------------------------ #
# Registry tests (sync)                                               #
# ------------------------------------------------------------------ #


def test_registry_get_image_returns_image_loader() -> None:
    loader = get("image")
    assert isinstance(loader, ImageLoader)


def test_registry_get_for_mime_png() -> None:
    loader = get_for_mime("image/png")
    assert isinstance(loader, ImageLoader)


def test_registry_get_for_mime_jpeg() -> None:
    loader = get_for_mime("image/jpeg")
    assert isinstance(loader, ImageLoader)


def test_registry_get_for_mime_webp() -> None:
    loader = get_for_mime("image/webp")
    assert isinstance(loader, ImageLoader)
