---
title: "Text Embeddings Inference (TEI)"
category: "infra"
icon: "⚙️"
usedInPipeline: ["ingestion", "retrieval"]
status: "in-use"
current:
  name: "TEI (self-hosted Docker)"
  tier: "free / open source"
  pros:
    - "Free Apache 2.0 — same software HuggingFace uses for paid endpoints"
    - "CPU and CUDA Docker images ready — text-embeddings-inference:cpu-1.5 for local dev"
    - "One software serves both embedding (port 8080) and reranker (port 8081)"
  cons:
    - "You are the SRE — patches, OOM events, GPU driver updates"
prodAlternative:
  name: "HuggingFace Inference Endpoints"
  tier: "managed / ~$0.50–$2 per GPU-hour"
  pros:
    - "Auto-scaling and multi-AZ — no ops overhead"
    - "Deploy the same TEI Docker image — zero application code change"
  why_better: "Scaling to many concurrent users requires GPU instances + autoscaling. HuggingFace Inference Endpoints and Modal both let you deploy the same TEI image with no code changes."
---

# Text Embeddings Inference (TEI)

## What it is

Text Embeddings Inference (TEI) is HuggingFace's production-grade Rust-based HTTP server for hosting embedding and reranker models. It loads a HuggingFace model (e.g. BGE-M3 or bge-reranker-v2-m3) from a local directory or the HuggingFace Hub and exposes it behind a simple REST API. It includes built-in dynamic request batching, Flash Attention v2 kernel optimisations (on supported hardware), and Prometheus metrics. ASAG runs two TEI containers: one for the embedding model on port 8080, and one for the reranker model on port 8081. TEI is the same software that HuggingFace uses to serve its commercial inference endpoints.

## Responsibilities

- Load and serve the BGE-M3 embedding model on port 8080.
- Load and serve the bge-reranker-v2-m3 reranker model on port 8081.
- Handle dynamic request batching — grouping incoming HTTP requests into efficient GPU/CPU batches automatically.
- Expose `/health`, `/metrics` (Prometheus), `/embed`, `/embed_sparse`, and `/rerank` endpoints.
- Does **not** own retrieval logic or decide when to embed — it is a dumb model server. All orchestration lives in `core/embeddings.py` and `core/reranker.py`.

## Interfaces

**Inbound (embedding — port 8080):**
```http
POST /embed
Content-Type: application/json
{ "inputs": ["text1", "text2"], "normalize": true }
→ [[0.12, -0.03, ...], ...]   (shape: [n, 1024])
```

**Inbound (sparse — port 8080):**
```http
POST /embed_sparse
{ "inputs": ["text1"] }
→ [{"token": "machine", "weight": 0.82}, ...]
```

**Inbound (rerank — port 8081):**
```http
POST /rerank
{ "query": "...", "texts": ["chunk1", "chunk2", ...] }
→ [{"index": 2, "score": 0.97}, {"index": 0, "score": 0.61}, ...]
```

**Liveness:** `GET /health` → `{ "status": "ok" }` on both ports.

## Implementation notes

`docker-compose.yml` snippet (two TEI services):
```yaml
services:
  tei-embeddings:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
    ports: ["8080:80"]
    environment:
      MODEL_ID: BAAI/bge-m3
      MAX_BATCH_TOKENS: "16384"
    volumes:
      - tei-model-cache:/data

  tei-reranker:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
    ports: ["8081:80"]
    environment:
      MODEL_ID: BAAI/bge-reranker-v2-m3
      MAX_BATCH_TOKENS: "8192"
    volumes:
      - tei-reranker-cache:/data

volumes:
  tei-model-cache:
  tei-reranker-cache:
```

Mounting named volumes for model cache avoids re-downloading the model (~500 MB) on every container restart.

To switch to GPU: replace `cpu-1.5` with `cuda-1.5` and add `deploy.resources.reservations.devices` for the GPU.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Embedding port | 8080 | |
| Reranker port | 8081 | |
| CPU throughput (embed) | ~100–400 tokens/s | 4-core VM; scales with core count |
| GPU throughput (embed) | ~5,000–15,000 tokens/s | With CUDA image |
| Memory (BGE-M3, CPU) | ~2 GB | |
| Memory (reranker, CPU) | ~1 GB | |
| Model cold start | ~30–60 s | First startup downloads model from HuggingFace Hub |
| Warm restart | ~5 s | Model loaded from volume cache |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Container OOM | Exit code 137; `/health` → 503 | Restart container; reduce `MAX_BATCH_TOKENS` | Embedding and/or reranking fails; ingestion queue backs up |
| HuggingFace Hub unreachable (cold start) | Container fails to start; download error in logs | Pre-populate Docker volume with model weights; mount at `/data` | Container cannot start without internet on cold boot |
| Port conflict | Docker bind error on startup | Change host port in `docker-compose.yml`; update `core/embeddings.py` base URL | TEI service unavailable until resolved |
| CUDA driver mismatch (GPU image) | Container crashes with CUDA error | Match image CUDA version to host driver; check with `nvidia-smi` | GPU service unavailable; fall back to CPU image |
| Flash Attention not supported on hardware | Warning in TEI logs; slower inference | Expected on CPU and older GPUs; no action required | Performance degraded but functional |

## Security & data handling

- **Authn:** no authentication on TEI endpoints. TEI is internal-only — bound to Docker's internal bridge network, not reachable from the public internet.
- **PII:** text chunks and queries are processed in-memory inside the TEI container. No data is persisted by TEI itself.
- **Data residency:** fully on-prem. Data does not leave the host machine.
- **Network isolation:** in `docker-compose.yml`, TEI containers are on an internal Docker network. Only FastAPI worker containers can reach ports 8080 and 8081.
- **Model integrity:** model weights are downloaded from HuggingFace Hub over HTTPS and cached in named volumes. Pin to a specific model revision for reproducibility.

## Observability

- Prometheus metrics at `http://localhost:8080/metrics` (embedding) and `http://localhost:8081/metrics` (reranker). Key metrics: `te_request_duration_seconds`, `te_batch_size`, `te_queue_size`, `te_tokens_total`.
- Docker health check: `HEALTHCHECK CMD curl -sf http://localhost:80/health || exit 1`.
- Alert: embedding p95 > 5 s per batch of 32 chunks → CPU saturated; queue backing up.
- Alert: reranker p95 > 1 s for 20-doc batch → CPU saturated; consider GPU instance.

## Scaling considerations

- **CPU is the bottleneck.** On a 4-core VM, the CPU image supports ~5 concurrent embed requests before queuing builds up. Add more CPU cores or switch to the CUDA image.
- **Dynamic batching:** TEI's built-in batcher groups concurrent requests, improving GPU/CPU utilisation without application code changes. Tune `MAX_BATCH_TOKENS` to balance latency and throughput.
- **Multiple instances:** run multiple TEI embedding containers behind a round-robin load balancer. Each instance is stateless; no coordination needed.
- **Production swap:** HuggingFace Inference Endpoints deploy the identical TEI Docker image with auto-scaling and multi-AZ. The only change needed is the base URL in `core/embeddings.py` and `core/reranker.py` — no model code changes.

## References

- [TEI GitHub](https://github.com/huggingface/text-embeddings-inference)
- [TEI Docker reference](https://huggingface.co/docs/text-embeddings-inference)
