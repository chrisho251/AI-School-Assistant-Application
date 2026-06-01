---
title: "BGE-M3"
category: "embedding"
icon: "🧠"
usedInPipeline: ["ingestion", "retrieval"]
status: "in-use"
current:
  name: "BGE-M3 (self-hosted via TEI)"
  tier: "free / self-hosted"
  pros:
    - "Multilingual — 100+ languages including Vietnamese"
    - "No rate limits — runs entirely on your hardware"
    - "Dense + sparse vectors in one model pass"
  cons:
    - "CPU-only TEI is slow — batching is critical"
    - "Requires Docker and ~2 GB RAM"
prodAlternative:
  name: "Cohere Embed v4"
  tier: "managed / paid"
  pros:
    - "Purpose-built for enterprise document retrieval"
    - "Accepts raw PDF pages as input — skips parsing entirely"
    - "128k context window, multimodal native"
  why_better: "Higher retrieval quality with no infra to manage. ~$0.10 per million tokens — cheap but always billable. Worth it once embedding latency or quality becomes the bottleneck."
---

# BGE-M3

## What it is

BGE-M3 is a multilingual transformer encoder developed by BAAI (Beijing Academy of Artificial Intelligence). A single forward pass produces three representation types: a 1024-dimensional dense vector, a sparse lexical weight vector compatible with BM25-style retrieval, and a ColBERT-style multi-vector representation for late interaction. ASAG uses the dense and sparse outputs for hybrid retrieval. The model handles sequences up to 8,192 tokens and supports 100+ languages, including Vietnamese — the primary non-English language in ASAG's target classrooms.

## Responsibilities

- Ingestion stage 3: embed each document chunk into a 1024-d dense vector and a sparse weight vector.
- Retrieval step 1: embed the incoming user query in the same vector space.
- Maintains the invariant that query and document embeddings share identical model weights (a requirement for cosine similarity to be meaningful).
- Does **not** own chunking, indexing, or retrieval logic — those are handled by `ingestion/pipeline.py` and `rag/retriever.py`.

## Interfaces

**Inbound:** `core/embeddings.py` sends HTTP POST requests. Payload format:
```json
{ "inputs": ["chunk text 1", "chunk text 2"], "normalize": true }
```

**Outbound:** none. The model is stateless per request; it does not call external services.

**Endpoints used (served by TEI on port 8080):**
- `POST /embed` → dense float32 vectors, shape `[n, 1024]`
- `POST /embed_sparse` → sparse token weights as `{"token": weight}` maps
- `GET /health` → liveness probe

## Implementation notes

TEI Docker image: `ghcr.io/huggingface/text-embeddings-inference:cpu-1.5`
Model: `BAAI/bge-m3` (pulled from HuggingFace Hub at container start)

```python
# src/asag/core/embeddings.py
import httpx

async def embed_dense(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8080/embed",
            json={"inputs": texts, "normalize": True},
        )
        r.raise_for_status()
        return r.json()  # List[List[float]], shape [len(texts), 1024]
```

Key config (`docker-compose.yml`):
- `MODEL_ID=BAAI/bge-m3`
- `MAX_BATCH_TOKENS=16384` — controls the largest single batch
- `MAX_CONCURRENT_REQUESTS=512`

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Dense vector dims | 1024 | float32 |
| Max input tokens | 8192 | model limit |
| CPU batch throughput | ~100–400 tokens/s | depends on CPU; measured on a 4-core VM |
| GPU batch throughput | ~5,000–15,000 tokens/s | with CUDA image |
| Memory footprint | ~2 GB RAM | CPU image |
| Cost per token | $0 | self-hosted |

> _Latency p50/p95 for a batch of 32 chunks to be benchmarked from `scripts/benchmark_embeddings.py` — not yet measured._

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| TEI container OOM | `docker inspect` shows exit code 137; `/health` returns 503 | Restart container; reduce `MAX_BATCH_TOKENS` | All ingestion jobs queue up; retrieval returns errors until TEI is back |
| Model weight download fails on cold start | Container exits on startup; logs show HTTP 404 from HF Hub | Pre-pull model weights into a named Docker volume; mount at `/data` | Entire embedding service unavailable |
| TEI port 8080 not reachable | `httpx.ConnectError` in `embeddings.py` | Circuit-break ingestion job; retry with exponential back-off | Ingestion fails gracefully; retrieval falls back to BM25-only (degraded mode) |
| Embedding dimension mismatch | `INSERT` into `chunks.embedding` fails with Postgres type error | Re-embed with correct model; migration needed if model changed | Data corruption if partially ingested — prevent by pinning model version |

## Security & data handling

- **Authn:** no auth on TEI endpoints. The service is internal-only — bound to `127.0.0.1` or a Docker internal network, not exposed to the public internet.
- **PII:** chunks sent to TEI may contain student-authored text. Data does not leave the host network (self-hosted). Dense vectors are opaque float arrays — they cannot be reversed to reconstruct the original text.
- **Data residency:** fully on-prem; no external API calls.
- **Encryption in transit:** HTTP within the Docker network (no TLS required for localhost). Add mTLS between services in a multi-node deployment.

## Observability

- TEI exposes a Prometheus `/metrics` endpoint on the same port. Key metrics: `te_request_duration_seconds`, `te_batch_size`, `te_queue_size`.
- `core/embeddings.py` wraps calls with `@observe()` from Langfuse (Phase 9+). Span name: `embed_dense` / `embed_sparse`.
- Alert threshold: p95 embedding latency > 5 s per batch of 32 chunks (CPU); > 200 ms (GPU).

## Scaling considerations

- **CPU bottleneck first:** on CPU-only TEI, a high ingestion volume (many teachers uploading large PDFs simultaneously) saturates the embedding service before any other component.
- **Horizontal scale:** run multiple TEI containers behind a load balancer; batching ensures GPU utilisation remains high.
- **Switch to CUDA image:** replacing `cpu-1.5` with `cuda-1.5` requires a GPU-enabled host but increases throughput 10–40×. Same Docker Compose change, zero code change in `embeddings.py`.
- **Above ~10M embeddings:** consider offloading to HuggingFace Inference Endpoints or Modal (same TEI image, auto-scaling, no code change).

## References

- [BGE-M3 paper](https://arxiv.org/abs/2402.03216)
- [HuggingFace model card](https://huggingface.co/BAAI/bge-m3)
- [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
