"""Slide generation — outline → Marp markdown → .pptx/.html → Storage + artifact row.

Pipeline (generate_slides):
    generate_outline → outline_to_marp (Jinja) → marp_render (Marp CLI subprocess,
    .pptx/.html) → upload to StorageBackend → artifacts row marked ``ready``.

The Marp step shells out, so it stays synchronous behind ``asyncio.to_thread``
(Windows' SelectorEventLoop, required by psycopg, cannot spawn async subprocesses).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from jinja2 import Environment, FileSystemLoader, select_autoescape
from psycopg_pool import AsyncConnectionPool

from asag.core.observability import traced
from asag.core.storage import StorageBackend, get_storage_backend
from asag.models.studio import Outline
from asag.studio.outline import generate_outline
from asag.studio.repository import StudioRepository

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# Autoescape only for HTML/XML; the Marp template is markdown and must stay raw.
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)

_CONTENT_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html",
}


@dataclass
class SlideDeck:
    """Result of ``generate_slides`` — the persisted artifact and its file URLs."""

    artifact_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    outline: Outline
    file_urls: dict[str, str]  # format ("pptx"/"html") → public URL


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #


def outline_to_marp(outline: Outline, *, template: str = "default.md.j2") -> str:
    """Render an Outline to Marp-flavoured markdown using a Jinja template."""
    return _JINJA_ENV.get_template(template).render(outline=outline)


def _marp_argv() -> list[str]:
    """Return the base argv to invoke Marp CLI (direct binary or via npx)."""
    marp = shutil.which("marp")
    if marp:
        return [marp]
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        # -y auto-installs the package on first run without an interactive prompt.
        return [npx, "-y", "@marp-team/marp-cli"]
    raise RuntimeError(
        "Marp CLI not found. Install it (`npm i -g @marp-team/marp-cli`) or ensure `npx` is on PATH."
    )


def _render_marp_sync(md_path: Path, out_path: Path, fmt: str) -> Path:
    """Blocking Marp render of *md_path* to *out_path* in *fmt* (pptx|html)."""
    # No --allow-local-files: decks reference no local paths, and the flag would let
    # raw LLM-generated markdown (e.g. ![](file:///...)) read arbitrary host files.
    argv = [*_marp_argv(), str(md_path), f"--{fmt}", "-o", str(out_path)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=600)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(
            f"Marp {fmt} render failed (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:500]}"
        )
    if not out_path.exists():
        raise RuntimeError(f"Marp reported success but {out_path} was not produced")
    return out_path


async def marp_render(md_path: Path, out_path: Path, fmt: str) -> Path:
    """Render *md_path* to *out_path* in *fmt* (``pptx`` or ``html``) via Marp CLI."""
    if fmt not in _CONTENT_TYPES:
        raise ValueError(f"Unsupported Marp format {fmt!r}; expected one of {list(_CONTENT_TYPES)}")
    return await asyncio.to_thread(_render_marp_sync, md_path, out_path, fmt)


# --------------------------------------------------------------------------- #
# Orchestrator                                                                 #
# --------------------------------------------------------------------------- #


@traced("studio.generate_slides")
async def generate_slides(
    notebook_id: uuid.UUID,
    *,
    pool: AsyncConnectionPool,
    storage: StorageBackend | None = None,
    n_slides: int = 10,
    model: str | None = None,
    formats: tuple[str, ...] = ("pptx", "html"),
) -> SlideDeck:
    """Generate a slide deck for a notebook and persist it as an artifact.

    Args:
        notebook_id: Notebook to build slides from.
        pool:        DB connection pool.
        storage:     Storage backend; defaults to the configured one.
        n_slides:    Target slide count.
        model:       Generator model; defaults to ``ASAG_LLM_GENERATOR``.
        formats:     Output formats to render and upload (``pptx``/``html``).

    Returns:
        A SlideDeck with the artifact id, outline, and per-format file URLs.

    Raises:
        ValueError:   If the notebook has no ingested chunks.
        RuntimeError: If Marp rendering fails (artifact is marked ``failed`` first).
    """
    store = storage or get_storage_backend()
    repo = StudioRepository(pool)

    outline = await generate_outline(notebook_id, pool=pool, n_slides=n_slides, model=model)
    artifact_id = await repo.create_artifact(notebook_id, kind="slide_deck", title=outline.title)

    try:
        markdown = outline_to_marp(outline)
        file_urls = await _render_and_upload(store, notebook_id, artifact_id, markdown, formats)
    except Exception as exc:
        await repo.mark_failed(artifact_id, error_message=str(exc))
        log.exception("generate_slides failed: notebook=%s artifact=%s", notebook_id, artifact_id)
        raise

    # The pptx is the primary deliverable; fall back to whatever was produced.
    primary_url = file_urls.get("pptx") or next(iter(file_urls.values()), "")
    await repo.mark_ready(
        artifact_id, file_url=primary_url, payload=outline.model_dump(mode="json")
    )
    log.info(
        "generate_slides: notebook=%s artifact=%s formats=%s", notebook_id, artifact_id, formats
    )
    return SlideDeck(
        artifact_id=artifact_id,
        notebook_id=notebook_id,
        title=outline.title,
        outline=outline,
        file_urls=file_urls,
    )


async def _render_and_upload(
    store: StorageBackend,
    notebook_id: uuid.UUID,
    artifact_id: uuid.UUID,
    markdown: str,
    formats: tuple[str, ...],
) -> dict[str, str]:
    """Render markdown to each format in a temp dir, upload, return format→URL."""
    file_urls: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="asag-marp-") as tmp:
        md_path = Path(tmp) / "deck.md"
        md_path.write_text(markdown, encoding="utf-8")
        for fmt in formats:
            out_path = Path(tmp) / f"deck.{fmt}"
            await marp_render(md_path, out_path, fmt)
            key = f"artifacts/{notebook_id}/{artifact_id}.{fmt}"
            url = await store.upload(key, out_path.read_bytes(), _CONTENT_TYPES[fmt])
            file_urls[fmt] = url
    return file_urls
