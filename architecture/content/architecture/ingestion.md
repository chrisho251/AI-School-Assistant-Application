---
title: "Ingestion Pipeline"
---

# Ingestion Pipeline (Pipeline 1)

> Turns a raw file uploaded by a teacher into searchable chunks with vector embeddings, asynchronously and idempotently.

## Why it exists

Retrieval quality and downstream LLM cost both depend on how documents are segmented and how accurately those segments are vectorized. Running this pipeline asynchronously at upload time means runtime retrieval is fast and deterministic — no parsing or embedding happens on the critical path of a student query.

## Stages

### Stage 0 — Persist
- File arrives at Supabase Storage.
- A row is inserted into `sources` with `status = pending` and the SHA-256 `checksum`.
- The checksum makes the pipeline idempotent: re-uploading the same file does not create duplicate chunks.

### Stage 1 — Load / Parse
Routed by MIME type:

| Source type | Loader |
|---|---|
| PDF, DOCX | **Docling** → markdown with preserved headings, tables, page numbers |
| PNG, JPG | **Gemini Vision** → dense academic caption stored as a text chunk |
| .py | Python `ast` module → one chunk per function / class |
| .ipynb | `nbformat` → one chunk per cell, preserving `cell_type` |

Output of stage 1: `list[Element]` with `{type, content, page, metadata}`.

### Stage 2 — Chunk
- **Text**: semantic chunker. Target ~1000 tokens per chunk with 150 token overlap. Splits prefer heading and section boundaries to keep meaning intact.
- **Code**: chunk per function / cell (already done in stage 1 for code; this stage just enforces size caps for huge functions).
- `tiktoken` counts tokens — the model's notion of a "word".

Output of stage 2: `list[Chunk]` with ordinal, page, content_type, source metadata. No vectors yet.

### Stage 3 — Embed
- Batch of ~32 chunks per call to the TEI service running **BGE-M3** on `localhost:8080`.
- For each chunk the service returns:
  - **Dense vector** (1024 dims): captures meaning. Used for semantic search.
  - **Sparse weights**: captures exact keywords. Used for BM25-style search.

### Stage 4 — Index
- Single transaction: `INSERT` all chunks with their embeddings into `chunks` table.
- HNSW index on `embedding`, GIN index on `sparse_vector` and `metadata` allow fast retrieval later.
- `sources.status` flips to `ready`.

## Failure modes and recovery

- If parsing fails → `sources.status = failed_at_parsing`, retry from stage 1.
- If TEI is down → `failed_at_embedding`, retry from stage 3 (parsed chunks are cached).
- If DB insert fails → transaction rolls back, no partial state.
- `tenacity` library handles transient HTTP errors with exponential backoff.

## Stage-level data contracts

| Between | Schema |
|---|---|
| 1 → 2 | `Element { type, content, page, metadata }` |
| 2 → 3 | `Chunk { ordinal, content, content_type, source_metadata }` |
| 3 → 4 | `Chunk + { embedding: list[float], sparse_vector: dict }` |

## Components on the diagram

- `docling` (stage 1, documents)
- `gemini-flash` (stage 1, image captioning)
- `bge-m3` + `tei` (stage 3)
- `pgvector` (stage 4)
- `supabase` (Storage in stage 0, Postgres in stage 4)

## Performance notes

- Stage 2 (chunking) runs on local CPU and is fast.
- Stage 3 (embedding) is the slow stage on CPU-only TEI — that's why batching matters and why benchmarking is on the build plan.
- Indexing cost (HNSW) is paid once at insert; queries pay an approximate-nearest-neighbour search cost that scales sublinearly.
