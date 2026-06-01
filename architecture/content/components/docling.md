---
title: "Docling"
category: "parsing"
icon: "📄"
usedInPipeline: ["ingestion"]
status: "in-use"
current:
  name: "Docling (self-hosted Python library)"
  tier: "free / self-hosted"
  pros:
    - "Free and private — no per-page cost, runs locally"
    - "97.9% table extraction accuracy in published benchmarks"
    - "Supports PDF, DOCX, PPTX, HTML, and image PDFs out of the box"
  cons:
    - "Slower than managed APIs on large workloads"
    - "CPU-heavy on big PDFs"
prodAlternative:
  name: "LlamaParse"
  tier: "managed / paid"
  pros:
    - "Faster on large workloads — processes pages in seconds"
    - "Better edge-case PDFs (complex forms, scanned medical documents)"
    - "No infra to manage"
  why_better: "~$0.003 per page with state-of-the-art table fidelity. A school with many teachers uploading hundreds of pages daily will hit Docling's CPU ceiling. For privacy-sensitive deployments, Docling stays."
---

# Docling

## What it is

Docling is IBM's open-source document parsing library (released 2024, MIT licence). It applies layout analysis, table structure recognition, and OCR to transform PDFs, DOCX, PPTX, and image documents into a structured intermediate representation, then exports clean Markdown with preserved tables, headings, captions, and page-number metadata. In published benchmarks it achieves 97.9% table extraction accuracy. It runs as a Python library — no network call, no per-page cost.

## Responsibilities

- Ingestion stage 1: convert uploaded documents (PDF, DOCX, PPTX, images) to structured Markdown.
- Attach per-element metadata: `page_number`, `is_table`, `is_heading`, `is_caption`, `bbox`.
- Handle multi-column layouts, scanned PDFs (OCR fallback), and embedded images.
- Does **not** own chunking, embedding, or storage — those are handled by downstream stages in `ingestion/pipeline.py`.

## Interfaces

**Inbound:** `ingestion/loaders/pdf.py` calls `DocumentConverter` with a file path. Input: a local file path to a PDF, DOCX, PPTX, or image.

**Outbound:** returns a `DoclingDocument` object; the loader calls `.export_to_markdown()` to produce the string consumed by the chunker.

**Public surface (Python API):**
```python
from docling.document_converter import DocumentConverter
converter = DocumentConverter()
result = converter.convert(source_path)
markdown_text: str = result.document.export_to_markdown()
```

No network calls — all computation is local.

## Implementation notes

Package: `docling >= 2.0` (installed via `uv`).

```python
# src/asag/ingestion/loaders/pdf.py
from docling.document_converter import DocumentConverter
from pathlib import Path

_converter = DocumentConverter()  # singleton — reuse across requests

async def load_pdf(path: Path) -> str:
    """Parse PDF and return Markdown with metadata annotations."""
    result = _converter.convert(str(path))
    return result.document.export_to_markdown()
```

Docling is CPU-bound. The `DocumentConverter` is not thread-safe for parallel calls with the same instance — use separate instances per worker or process in a job queue (Inngest worker, Phase 9+).

Key config: none required for basic use. For OCR acceleration: set `ocr_options.use_gpu=True` if a GPU is present.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Parse time (10-page text PDF) | ~2–5 s | CPU, no OCR |
| Parse time (10-page scanned PDF) | ~15–45 s | CPU + OCR |
| Parse time (DOCX) | ~1–3 s | CPU |
| Table accuracy | 97.9% | Published benchmark vs LlamaParse, Unstructured |
| Memory per parse | ~500 MB | Peak during layout model inference |
| Cost per page | $0 | Self-hosted |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Password-protected PDF | `docling.exceptions.EncryptedPdfError` | Return error to uploader; record `sources.ingestion_status = failed` | Single source; other sources unaffected |
| Corrupt or truncated file | Unhandled exception or empty output | Log + mark source failed; notify teacher via UI | Single source |
| OCR timeout on huge scanned PDF | Worker timeout (Inngest max job duration) | Split PDF into batches of ≤ 50 pages; re-enqueue parts | Partial ingestion; teacher sees `in_progress` status |
| Layout model OOM | Worker process killed | Reduce concurrency to 1 worker per CPU; add swap | Worker restarts; job retried up to 3 times |
| Docling version incompatibility | Build-time pip error | Pin `docling==2.x.y` in `pyproject.toml` | Build fails; caught in CI before deploy |

## Security & data handling

- **PII:** uploaded documents may contain student names, exam data, and personally identifiable content. Docling processes files locally — no data leaves the host. Parsed Markdown is stored only in Postgres (`chunks.content`), controlled by RLS.
- **File validation:** `loaders/` validates MIME type and file size before passing to Docling. Maximum file size: 25 MB (enforced in FastAPI route, not Docling).
- **Authn:** Docling itself has no auth layer. Access is gated upstream by the FastAPI JWT middleware.
- **Encryption:** parsed Markdown stored in Postgres inherits Supabase's at-rest encryption. Source files in Supabase Storage are encrypted at rest (AES-256).

## Observability

- Per-source parse duration logged to `docs/daily-logs/` (pre-Phase 52); Langfuse span `parse_document` after Phase 52.
- `sources.ingestion_status` column tracks: `pending → parsing → chunking → embedding → ready / failed`.
- Alert: if `sources.ingestion_status = parsing` for > 10 minutes → trigger retry.

## Scaling considerations

- **CPU is the bottleneck.** For > 50 concurrent uploads, run multiple Inngest workers on separate CPU cores. Docling's layout model is the heaviest step.
- **GPU acceleration:** Docling supports GPU for OCR (`easyocr` backend) but the gain is small unless > 30% of uploads are scanned PDFs.
- **Production swap:** LlamaParse API processes pages in seconds and handles edge-case scanned documents better. Switch is isolated to `ingestion/loaders/pdf.py` — chunker and embedder are unaffected.

## References

- [Docling GitHub](https://github.com/DS4SD/docling)
- [PDF parsing benchmark — Docling vs LlamaParse vs Unstructured](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/)
