"""Integration test: ImageLoader → pipeline → DB.

Requires:
  - SUPABASE_DB_URL configured and reachable (port 5432 open)
  - GEMINI_API_KEY configured (calls real Gemini Vision API)

Run from home / mobile data:
    uv run pytest tests/integration/test_image_loader.py -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import uuid

from PIL import Image, ImageDraw
import psycopg
import pytest

from asag.config import ConfigError, get_settings
from asag.core.db import create_pool
from asag.ingestion.loaders.image import ImageLoader
from asag.models.ingestion import ContentType

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


@pytest.fixture(scope="session")
def db_url() -> str:
    cfg = get_settings()
    try:
        return cfg.require_db_url()
    except ConfigError:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture(scope="session")
def gemini_key() -> str:
    cfg = get_settings()
    if not cfg.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not configured")
    return cfg.gemini_api_key


@pytest.fixture(scope="session")
def sample_chart_png(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a simple bar-chart PNG using Pillow."""
    tmp = tmp_path_factory.mktemp("images")
    path = tmp / "sample_chart.png"
    img = Image.new("RGB", (400, 300), color="white")
    draw = ImageDraw.Draw(img)
    # Axes
    draw.line([(50, 250), (350, 250)], fill="black", width=2)  # x-axis
    draw.line([(50, 50), (50, 250)], fill="black", width=2)  # y-axis
    # Bars
    for i, (label, height, colour) in enumerate(
        [
            ("Q1", 100, "#4472C4"),
            ("Q2", 150, "#ED7D31"),
            ("Q3", 80, "#A9D18E"),
            ("Q4", 200, "#FF0000"),
        ]
    ):
        x0 = 70 + i * 70
        draw.rectangle([x0, 250 - height, x0 + 40, 250], fill=colour)
        draw.text((x0 + 5, 255), label, fill="black")
    draw.text((140, 20), "Quarterly Revenue (USD M)", fill="black")
    img.save(path)
    return path


@pytest.fixture(scope="session")
def sample_slide_png(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a simple slide-like PNG using Pillow."""
    tmp = tmp_path_factory.mktemp("slides")
    path = tmp / "sample_slide.png"
    img = Image.new("RGB", (800, 600), color="#1F4E79")
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 760, 560], fill="white")
    draw.text((60, 60), "Introduction to Machine Learning", fill="#1F4E79")
    draw.text((60, 120), "• Supervised Learning: labeled data", fill="black")
    draw.text((60, 160), "• Unsupervised Learning: pattern discovery", fill="black")
    draw.text((60, 200), "• Reinforcement Learning: reward signals", fill="black")
    draw.text((60, 260), "Key algorithms: SVM, Decision Trees, Neural Networks", fill="#555")
    img.save(path)
    return path


# ------------------------------------------------------------------ #
# ImageLoader unit-level integration (real Gemini, no DB)             #
# ------------------------------------------------------------------ #


@pytest.mark.integration
@pytest.mark.live_llm
async def test_integ_image_loader_returns_caption(gemini_key: str, sample_chart_png: Path) -> None:
    """Real Gemini Vision call produces a non-empty caption."""
    loader = ImageLoader()
    elements = await loader.parse(sample_chart_png)

    assert len(elements) == 1
    el = elements[0]
    assert el.content_type == ContentType.image_caption
    assert len(el.content) > 50, "Caption must be substantive (>50 chars)"
    assert el.page_number is None


@pytest.mark.integration
@pytest.mark.live_llm
async def test_integ_image_loader_slide_caption(gemini_key: str, sample_slide_png: Path) -> None:
    """Gemini Vision captions the slide image correctly."""
    loader = ImageLoader()
    elements = await loader.parse(sample_slide_png)

    assert len(elements) == 1
    # Caption should mention key slide concepts
    caption_lower = elements[0].content.lower()
    assert any(kw in caption_lower for kw in ["machine learning", "supervised", "learning"])


# ------------------------------------------------------------------ #
# Pipeline integration: image + PDF in same notebook → both indexed   #
# ------------------------------------------------------------------ #


@pytest.mark.integration
@pytest.mark.live_llm
async def test_integ_pdf_and_image_in_same_notebook(
    db_url: str,
    gemini_key: str,
    sample_chart_png: Path,
) -> None:
    """A notebook can contain both PDF and image sources; both produce chunks."""
    from unittest.mock import patch

    from asag.ingestion.pipeline import ingest_source
    from asag.models.ingestion import ContentType, Element

    ids = {
        "org": uuid.uuid4(),
        "user": uuid.uuid4(),
        "class_": uuid.uuid4(),
        "notebook": uuid.uuid4(),
        "pdf_src": uuid.uuid4(),
        "img_src": uuid.uuid4(),
    }

    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        # ---- Seed ----
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
                (str(ids["org"]), "Multimodal Org", f"mm-{ids['org'].hex[:8]}"),
            )
            await conn.execute(
                "INSERT INTO users (id, org_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s)",
                (str(ids["user"]), str(ids["org"]), "mm@test.com", "Teacher", "teacher"),
            )
            await conn.execute(
                "INSERT INTO classes (id, org_id, name, teacher_id) VALUES (%s, %s, %s, %s)",
                (str(ids["class_"]), str(ids["org"]), "Class", str(ids["user"])),
            )
            await conn.execute(
                "INSERT INTO notebooks (id, class_id, owner_id, title) VALUES (%s, %s, %s, %s)",
                (str(ids["notebook"]), str(ids["class_"]), str(ids["user"]), "Multimodal NB"),
            )
            # PDF source
            await conn.execute(
                """INSERT INTO sources
                   (id, notebook_id, source_type, original_filename, storage_url, ingestion_status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    str(ids["pdf_src"]),
                    str(ids["notebook"]),
                    "pdf",
                    "doc.pdf",
                    "test/doc.pdf",
                    "pending",
                ),
            )
            # Image source
            await conn.execute(
                """INSERT INTO sources
                   (id, notebook_id, source_type, original_filename, storage_url, ingestion_status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    str(ids["img_src"]),
                    str(ids["notebook"]),
                    "image",
                    "chart.png",
                    "test/chart.png",
                    "pending",
                ),
            )
            await conn.commit()

        # PDF fake elements (mocked loader)
        pdf_elements = [
            Element(
                content="Machine learning is a branch of AI.",
                content_type=ContentType.text,
                page_number=1,
                metadata={"label": "text"},
            ),
            Element(
                content="Neural networks are used in deep learning.",
                content_type=ContentType.text,
                page_number=2,
                metadata={"label": "text"},
            ),
        ]

        mock_storage = MagicMock()
        mock_storage.download = AsyncMock(return_value=b"fake bytes")
        mock_storage.get_public_url = AsyncMock(return_value="http://storage/test/chart.png")

        # Ingest PDF (mocked loader)
        with patch("asag.ingestion.pipeline.loader_registry.get") as mock_get:
            mock_loader = MagicMock()
            mock_loader.parse = AsyncMock(return_value=pdf_elements)
            mock_get.return_value = mock_loader
            pdf_result = await ingest_source(ids["pdf_src"], pool=pool, storage=mock_storage)

        assert pdf_result.status == "ready"
        assert pdf_result.chunks_written > 0

        # Ingest image (real Gemini via ImageLoader, mock storage download)
        real_image_bytes = sample_chart_png.read_bytes()
        mock_storage.download = AsyncMock(return_value=real_image_bytes)

        img_result = await ingest_source(ids["img_src"], pool=pool, storage=mock_storage)

        assert img_result.status == "ready"
        assert img_result.chunks_written >= 1

        # Verify both sources have chunks in the same notebook
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT source_id, content_type FROM chunks WHERE notebook_id = %s ORDER BY created_at",
                (str(ids["notebook"]),),
            )
            rows = await cur.fetchall()
            source_ids_in_db = {str(r[0]) for r in rows}
            content_types = {r[1] for r in rows}

            assert str(ids["pdf_src"]) in source_ids_in_db
            assert str(ids["img_src"]) in source_ids_in_db
            assert "image_caption" in content_types

    finally:
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            await conn.execute(
                "DELETE FROM chunks   WHERE notebook_id = %s", (str(ids["notebook"]),)
            )
            await conn.execute(
                "DELETE FROM sources  WHERE notebook_id = %s", (str(ids["notebook"]),)
            )
            await conn.execute("DELETE FROM notebooks WHERE id = %s", (str(ids["notebook"]),))
            await conn.execute("DELETE FROM classes  WHERE id = %s", (str(ids["class_"]),))
            await conn.execute("DELETE FROM users    WHERE id = %s", (str(ids["user"]),))
            await conn.execute("DELETE FROM organizations WHERE id = %s", (str(ids["org"]),))
            await conn.commit()
        await pool.close()
