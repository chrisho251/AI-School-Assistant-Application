"""Benchmark per-stage ingestion timing across N sample PDFs.

Measures: Docling loader, semantic chunker, TEI embedder (if available).
Prints p50/p95 per stage and a per-file breakdown table.

Usage:
    uv run python scripts/benchmark_ingestion.py path/to/file.pdf [more.pdf ...]
    uv run python scripts/benchmark_ingestion.py          # scans tests/fixtures/sample_pdfs/
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import statistics
import sys
import time
import uuid

import httpx
from rich.console import Console
from rich.table import Table

from asag.config import get_settings
from asag.core.embeddings import EmbeddingClient
from asag.ingestion import chunkers as chunker_registry
from asag.ingestion import loaders as loader_registry
from asag.models.ingestion import Chunk, Element

console = Console()

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "sample_pdfs"
EMBED_BATCH = 32


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


async def run_loader(path: Path) -> tuple[list[Element], float]:
    loader = loader_registry.get("pdf")
    t0 = time.perf_counter()
    elements = await loader.parse(path)
    return elements, time.perf_counter() - t0


def run_chunker(elements: list[Element]) -> tuple[list[Chunk], float]:
    chunker = chunker_registry.get("semantic")
    t0 = time.perf_counter()
    chunks = chunker.chunk(
        elements,
        source_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
    )
    return chunks, time.perf_counter() - t0


async def run_embedder(
    chunks: list[Chunk],
    client: EmbeddingClient,
) -> float:
    t0 = time.perf_counter()
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        await client.embed_texts([c.content for c in batch])
    return time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Per-file benchmark
# ---------------------------------------------------------------------------


async def benchmark_file(
    path: Path,
    embed_client: EmbeddingClient | None,
) -> dict[str, object]:
    elements, loader_s = await run_loader(path)
    chunks, chunker_s = run_chunker(elements)
    embed_s: float | None = None
    if embed_client and chunks:
        embed_s = await run_embedder(chunks, embed_client)
    return {
        "file": path.name,
        "elements": len(elements),
        "chunks": len(chunks),
        "loader_s": loader_s,
        "chunker_s": chunker_s,
        "embed_s": embed_s,
    }


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


def _pct(values: list[float], pct: float) -> float:
    """Return the *pct* percentile (0.0–1.0) of *values*."""
    s = sorted(values)
    idx = max(0, int(pct * len(s)) - 1)
    return s[idx]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(paths: list[Path]) -> None:
    cfg = get_settings()

    # Try to reach TEI for embedding benchmark
    embed_client: EmbeddingClient | None = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            r = await http.get(f"{cfg.tei_embed_url}/health")
            if r.status_code == 200:
                embed_client = EmbeddingClient(cfg.tei_embed_url)
                console.print(f"[green]TEI reachable[/green] at {cfg.tei_embed_url}")
    except Exception:
        console.print(
            f"[yellow]TEI not reachable[/yellow] ({cfg.tei_embed_url}) — "
            "embedding stage will be skipped. Start docker compose to include it."
        )

    if not paths:
        console.print(
            "[yellow]No PDF paths supplied.[/yellow]\n"
            "Put sample PDFs in [cyan]tests/fixtures/sample_pdfs/[/cyan] or pass them as args:\n"
            "  uv run python scripts/benchmark_ingestion.py path/to/file.pdf"
        )
        return

    console.print(f"\nBenchmarking [bold]{len(paths)}[/bold] file(s)...\n")

    results: list[dict[str, object]] = []
    per_file_table = Table(title="Per-file breakdown", show_lines=False)
    per_file_table.add_column("File", no_wrap=True)
    per_file_table.add_column("Elements", justify="right")
    per_file_table.add_column("Chunks", justify="right")
    per_file_table.add_column("Loader (ms)", justify="right")
    per_file_table.add_column("Chunker (ms)", justify="right")
    per_file_table.add_column("Embed (ms)", justify="right")
    per_file_table.add_column("Total (ms)", justify="right")

    for path in paths:
        console.print(f"  [cyan]{path.name}[/cyan]...", end=" ")
        try:
            r = await benchmark_file(path, embed_client)
            results.append(r)
            loader_ms = float(r["loader_s"]) * 1000  # type: ignore[arg-type]
            chunker_ms = float(r["chunker_s"]) * 1000  # type: ignore[arg-type]
            embed_ms = float(r["embed_s"]) * 1000 if r["embed_s"] is not None else None  # type: ignore[arg-type]
            total_ms = loader_ms + chunker_ms + (embed_ms or 0.0)
            per_file_table.add_row(
                str(r["file"]),
                str(r["elements"]),
                str(r["chunks"]),
                f"{loader_ms:.0f}",
                f"{chunker_ms:.0f}",
                f"{embed_ms:.0f}" if embed_ms is not None else "—",
                f"{total_ms:.0f}",
            )
            console.print(f"[green]OK[/green] chunks={r['chunks']} total={total_ms:.0f}ms")
        except Exception as exc:
            console.print(f"[red]FAILED[/red] — {exc}")

    if not results:
        return

    console.print()
    console.print(per_file_table)

    # Summary p50/p95
    loader_times_ms = [float(r["loader_s"]) * 1000 for r in results]
    chunker_times_ms = [float(r["chunker_s"]) * 1000 for r in results]
    embed_times_ms = [float(r["embed_s"]) * 1000 for r in results if r["embed_s"] is not None]  # type: ignore[arg-type]
    total_times_ms = [
        float(r["loader_s"]) * 1000
        + float(r["chunker_s"]) * 1000
        + (float(r["embed_s"]) * 1000 if r["embed_s"] is not None else 0.0)  # type: ignore[arg-type]
        for r in results
    ]

    summary = Table(title="Stage timing summary (ms)")
    summary.add_column("Stage")
    summary.add_column("min", justify="right")
    summary.add_column("p50", justify="right")
    summary.add_column("p95", justify="right")
    summary.add_column("max", justify="right")

    def add_row(label: str, times: list[float]) -> None:
        if not times:
            summary.add_row(label, "—", "—", "—", "—")
            return
        summary.add_row(
            label,
            f"{min(times):.0f}",
            f"{statistics.median(times):.0f}",
            f"{_pct(times, 0.95):.0f}",
            f"{max(times):.0f}",
        )

    add_row("Loader (Docling PDF)", loader_times_ms)
    add_row("Chunker (semantic)", chunker_times_ms)
    add_row("Embedder (TEI BGE-M3)", embed_times_ms)
    add_row("Total (excl. DB write)", total_times_ms)

    console.print()
    console.print(summary)
    console.print(
        f"\n[dim]n={len(results)}  "
        f"avg_elements={statistics.mean(float(r['elements']) for r in results):.0f}  "  # type: ignore[arg-type]
        f"avg_chunks={statistics.mean(float(r['chunks']) for r in results):.0f}[/dim]"
    )


if __name__ == "__main__":
    pdf_args = [Path(p) for p in sys.argv[1:] if p.endswith(".pdf")]
    if not pdf_args:
        # Fall back to fixture dir
        pdf_args = sorted(FIXTURE_DIR.glob("*.pdf"))

    asyncio.run(main(pdf_args))
