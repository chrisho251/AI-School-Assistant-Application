---
title: "bge-reranker-v2-m3"
category: "reranker"
icon: "🎯"
usedInPipeline: ["retrieval"]
status: "in-use"
current:
  name: "bge-reranker-v2-m3 (self-hosted via TEI)"
  tier: "free / self-hosted"
  pros:
    - "Free and private — no data leaves your network"
    - "Multilingual — same language coverage as BGE-M3"
    - "Adds ~17 percentage points of Recall@5 vs hybrid alone"
  cons:
    - "CPU rerank on 20 docs takes 200–500 ms"
prodAlternative:
  name: "Cohere Rerank 3.5"
  tier: "managed / paid"
  pros:
    - "Stronger English-language ranking quality"
    - "Hosted on dedicated GPUs — lower p99 latency"
    - "Returns calibrated scores for thresholding irrelevant chunks"
  why_better: "If rerank latency dominates p95, a hosted reranker on dedicated GPUs is faster. Cohere Rerank 3.5 returns calibrated scores you can threshold on, dropping irrelevant chunks before they reach the LLM. ~$1 per 1k rerank calls."
---

# bge-reranker-v2-m3

## What it is

bge-reranker-v2-m3 is a cross-encoder reranker model from BAAI. Unlike a bi-encoder (which scores query and document independently), a cross-encoder concatenates the query and document text into a single input sequence and runs a joint transformer forward pass, producing a single relevance score. This joint attention mechanism provides significantly higher ranking accuracy than bi-encoder similarity at the cost of requiring a separate inference call per candidate document. ASAG uses it as the final filtering step after RRF fusion to reduce 20 candidates to 5–8 before LLM generation.

## Responsibilities

- Retrieval step 4: receive the original query + 20 candidate chunks from the RRF merge step.
- Score each (query, chunk) pair independently and return a ranked list.
- Pass the top 5–8 highest-scoring chunks to the generation LLM.
- Does **not** perform initial retrieval, embedding, or generation — only reranks an existing candidate set.

## Interfaces

**Inbound:** `core/reranker.py` sends HTTP POST to TEI at port 8081. Payload:
```json
{
  "query": "user query text",
  "texts": ["chunk 1 text", "chunk 2 text", "..."],
  "raw_scores": false
}
```

**Outbound:** none. Stateless per request.

**Endpoints used (served by TEI on port 8081):**
- `POST /rerank` → list of `{index, score}` objects, sorted descending
- `GET /health` → liveness probe

## Implementation notes

TEI Docker image: `ghcr.io/huggingface/text-embeddings-inference:cpu-1.5`
Model: `BAAI/bge-reranker-v2-m3`

```python
# src/asag/core/reranker.py
import httpx

async def rerank(query: str, chunks: list[str]) -> list[int]:
    """Return indices of chunks sorted by relevance (most relevant first)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "http://localhost:8081/rerank",
            json={"query": query, "texts": chunks, "raw_scores": False},
        )
        r.raise_for_status()
        ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)
        return [item["index"] for item in ranked]
```

Key config (`docker-compose.yml`):
- `MODEL_ID=BAAI/bge-reranker-v2-m3`
- `MAX_BATCH_TOKENS=8192` — per-pair limit; 20 pairs × (query + chunk) must fit within limit

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Candidate set size | 20 docs | from RRF fusion step |
| Output set size | top 5–8 | passed to LLM |
| CPU latency (20 docs) | 200–500 ms | measured in bge-reranker paper |
| Memory footprint | ~1 GB RAM | lighter than BGE-M3 |
| Cost per call | $0 | self-hosted |
| Recall@5 improvement | +17 pp | vs hybrid-only (benchmark: proposal.md §6.2) |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| TEI reranker OOM | `/health` returns 503 | Restart container; reduce batch size | Retrieval pipeline falls back to returning top-20 RRF results without reranking (degraded quality, no outage) |
| Reranker timeout (slow CPU) | `httpx.TimeoutException` after 30 s | Return top-20 RRF order as fallback; log warning to Langfuse | User sees lower-quality context in LLM answer |
| Model weight unavailable | Container exits at startup | Pre-pull model into Docker volume | Reranker service down; fallback as above |
| All 20 candidates score below threshold | No natural cutoff issue — top-k is always returned | Set a minimum score threshold and return fewer chunks if all low | LLM may receive irrelevant context; generator prompt handles gracefully |

## Security & data handling

- **Authn:** none — TEI reranker is internal-only, bound to Docker network, not exposed to the internet.
- **PII:** query text and chunk content (potentially student work) are processed in-memory. Data does not leave the host.
- **Data residency:** fully on-prem.
- **Encryption in transit:** HTTP within Docker network. Apply mTLS in multi-node deployments.

## Observability

- TEI exposes Prometheus `/metrics` (same port 8081). Key metric: `te_request_duration_seconds` labelled `rerank`.
- `core/reranker.py` wraps calls with `@observe()` (Langfuse, Phase 9+). Span name: `rerank`.
- Alert threshold: rerank p95 latency > 1 s for 20-doc batches on CPU.

## Scaling considerations

- **CPU is the bottleneck.** Cross-encoders are inherently serial — they cannot precompute embeddings for documents. Scaling throughput means adding more TEI instances and routing requests with a load balancer.
- **Candidate pool size matters more than throughput:** reducing candidates from 30 to 20 before calling the reranker cuts latency by ~33% with minimal recall loss.
- **GPU acceleration:** the CUDA TEI image reduces rerank time from 200–500 ms to < 30 ms. Required if the retrieval pipeline p95 target is < 500 ms end-to-end.
- **Production swap:** Cohere Rerank 3.5 (hosted) offers sub-100 ms p99 at scale; the swap requires one config change in `config.py` + a different endpoint in `reranker.py`.

## References

- [bge-reranker-v2-m3 HuggingFace card](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [Cross-encoder vs bi-encoder explainer](https://www.sbert.net/examples/applications/cross-encoder/README.html)
