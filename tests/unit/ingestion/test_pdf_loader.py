"""Unit tests for PdfLoader — Docling is mocked; no real PDF parsing runs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from asag.ingestion.loaders import get, get_for_mime, register
from asag.ingestion.loaders.pdf import PdfLoader
from asag.models.ingestion import ContentType, Element

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


@pytest.fixture
def fake_pdf(tmp_path: Path) -> Path:
    """A file that satisfies PdfLoader's path argument (Docling is mocked)."""
    p = tmp_path / "sample.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def _make_text_item(text: str, page: int | None = 1) -> MagicMock:
    """Build a duck-typed text item that PdfLoader._is_text() accepts."""
    item = MagicMock()
    item.text = text
    item.label = "text"
    del item.export_to_markdown  # not a table
    item.prov = [MagicMock(page_no=page)] if page is not None else []
    return item


def _make_table_item(markdown: str, page: int | None = 2) -> MagicMock:
    """Build a duck-typed table item that PdfLoader._is_table() accepts."""
    item = MagicMock()
    item.export_to_markdown = MagicMock(return_value=markdown)
    item.prov = [MagicMock(page_no=page)] if page is not None else []
    return item


def _build_mock_result(*items: MagicMock) -> MagicMock:
    """Wrap items into a mock ConversionResult."""
    doc = MagicMock()
    doc.iterate_items.return_value = [(item, 0) for item in items]
    result = MagicMock()
    result.document = doc
    return result


# ------------------------------------------------------------------ #
# PdfLoader.parse() tests (async)                                     #
# ------------------------------------------------------------------ #


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_text_elements(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """Loader extracts text items with correct content and page number."""
    text_item = _make_text_item("Introduction to machine learning.", page=1)
    mock_dc.return_value.convert.return_value = _build_mock_result(text_item)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert len(elements) == 1
    e = elements[0]
    assert e.content == "Introduction to machine learning."
    assert e.content_type == ContentType.text
    assert e.page_number == 1


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_table_elements(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """Loader extracts table items as table content_type."""
    table_md = "| A | B |\n|---|---|\n| 1 | 2 |"
    table_item = _make_table_item(table_md, page=3)
    mock_dc.return_value.convert.return_value = _build_mock_result(table_item)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert len(elements) == 1
    e = elements[0]
    assert e.content == table_md
    assert e.content_type == ContentType.table
    assert e.page_number == 3


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_mixed_elements(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """Loader handles mixed text + table items in order."""
    items = [
        _make_text_item("Chapter 1", page=1),
        _make_table_item("| X |\n|---|\n| 5 |", page=1),
        _make_text_item("Some paragraph text.", page=2),
    ]
    mock_dc.return_value.convert.return_value = _build_mock_result(*items)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert len(elements) == 3
    assert elements[0].content_type == ContentType.text
    assert elements[1].content_type == ContentType.table
    assert elements[2].content_type == ContentType.text


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_skips_empty_content(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """Loader skips text items with whitespace-only content."""
    items = [
        _make_text_item("   ", page=1),  # whitespace only → skip
        _make_text_item("Real content", page=1),
    ]
    mock_dc.return_value.convert.return_value = _build_mock_result(*items)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert len(elements) == 1
    assert elements[0].content == "Real content"


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_page_number_none_when_no_prov(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """Items without provenance get page_number=None."""
    item = _make_text_item("No page info", page=None)
    mock_dc.return_value.convert.return_value = _build_mock_result(item)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert elements[0].page_number is None


@patch("asag.ingestion.loaders.pdf.DocumentConverter")
async def test_parse_returns_element_instances(mock_dc: MagicMock, fake_pdf: Path) -> None:
    """All returned objects are Element instances."""
    items = [_make_text_item("abc", page=1), _make_table_item("| a |", page=2)]
    mock_dc.return_value.convert.return_value = _build_mock_result(*items)

    loader = PdfLoader()
    elements = await loader.parse(fake_pdf)

    assert all(isinstance(e, Element) for e in elements)


# ------------------------------------------------------------------ #
# Registry tests (sync)                                               #
# ------------------------------------------------------------------ #


def test_registry_get_pdf_returns_pdf_loader() -> None:
    loader = get("pdf")
    assert isinstance(loader, PdfLoader)


def test_registry_get_for_mime_pdf() -> None:
    loader = get_for_mime("application/pdf")
    assert isinstance(loader, PdfLoader)


def test_registry_get_unknown_raises() -> None:
    with pytest.raises(KeyError, match="No loader registered"):
        get("nonexistent_format")


def test_registry_get_for_mime_unknown_raises() -> None:
    with pytest.raises(KeyError, match="No loader for MIME"):
        get_for_mime("application/octet-stream")


def test_registry_register_custom_loader() -> None:
    """Custom loaders can be registered and retrieved."""
    from asag.ingestion.loaders.base import Loader

    class FakeLoader(Loader):
        async def parse(self, file_path: Path) -> list[Element]:
            return []

    register("test_custom", FakeLoader)
    loader = get("test_custom")
    assert isinstance(loader, FakeLoader)
