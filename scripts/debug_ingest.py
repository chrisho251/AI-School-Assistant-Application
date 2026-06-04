"""Debug helper — run ingestion stages directly on a local PDF to surface tracebacks.

Usage:
    $env:PYTHONIOENCODING="utf-8"; uv run python scripts/debug_ingest.py "E:\\study\\ASAG-sample\\sample-pdf\\diagnostics-14-01182-v2.pdf"
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import traceback
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(pdf_path: str) -> None:
    from asag.config import get_settings
    from asag.core.embeddings import EmbeddingClient
    from asag.ingestion import chunkers as chunker_registry
    from asag.ingestion.loaders.pdf import PdfLoader

    path = Path(pdf_path)
    print(f"\n[1] Parsing PDF with Docling: {path.name} ...")
    try:
        elements = await PdfLoader().parse(path)
        print(f"    OK — {len(elements)} elements")
        for el in elements[:3]:
            print(f"      - {el.content_type} p{el.page_number}: {el.content[:60]!r}")
    except Exception:
        print("    FAILED at Docling parse:")
        traceback.print_exc()
        return

    print("\n[2] Chunking ...")
    try:
        chunker = chunker_registry.get("semantic")
        chunks = chunker.chunk(elements, source_id=uuid.uuid4(), notebook_id=uuid.uuid4())
        print(f"    OK — {len(chunks)} chunks")
    except Exception:
        print("    FAILED at chunking:")
        traceback.print_exc()
        return

    print("\n[3] Embedding via TEI (first batch) ...")
    try:
        cfg = get_settings()
        client = EmbeddingClient(cfg.tei_embed_url)
        results = await client.embed_texts([c.content for c in chunks[:2]])
        print(f"    OK — {len(results)} embeddings, dim={len(results[0].dense)}")
        await client._http.aclose()
    except Exception:
        print(f"    FAILED at embedding (TEI url={get_settings().tei_embed_url}):")
        traceback.print_exc()
        return

    print("\nAll stages OK ✅")


if __name__ == "__main__":
    pdf = (
        sys.argv[1]
        if len(sys.argv) > 1
        else r"E:\study\ASAG-sample\sample-pdf\diagnostics-14-01182-v2.pdf"
    )
    asyncio.run(main(pdf))
