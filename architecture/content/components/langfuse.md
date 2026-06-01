---
title: "Langfuse"
category: "observability"
icon: "📊"
usedInPipeline: ["qa", "assessment", "slides"]
status: "in-use"
current:
  name: "Langfuse (self-hosted Docker)"
  tier: "free / self-hosted"
  pros:
    - "Free MIT licence — no per-trace pricing"
    - "Traces never leave your infrastructure"
    - "First-class LiteLLM integration — minimal instrumentation code"
    - "Eval features built-in for later phases"
  cons:
    - "You are responsible for patching, backups, and uptime"
prodAlternative:
  name: "Langfuse Cloud"
  tier: "managed / ~$20/month starter"
  pros:
    - "No ops overhead — Langfuse hosts and backs up everything"
    - "Alerting, SSO, and SOC2 compliance"
    - "Same SDK — zero code change to migrate"
  why_better: "At scale, an SRE won't want to maintain another Postgres + UI. Langfuse Cloud is the lowest-friction upgrade — same SDK, just change the endpoint URL."
---

# Langfuse

## What it is

Langfuse is an open-source LLM observability and evaluation platform (MIT licence). It captures structured traces of every AI pipeline execution — model inputs, outputs, latency, token usage, and cost — and stores them as hierarchical span trees. ASAG instruments its RAG, assessment, and slide generation pipelines with Langfuse traces starting in Phase 9 of the build plan. Before Phase 9, equivalent data is logged as structured JSON to `docs/daily-logs/`. Langfuse also supports prompt versioning and human/LLM-based evaluation frameworks.

## Responsibilities

- Capture the full RAG trace as a tree: retrieve → rerank → generate → (grade, if assessment).
- Store prompt versions and map each trace to the prompt version that produced it.
- Track token usage and inferred cost per user, per notebook, and per pipeline for quota monitoring.
- Provide the evaluation harness for measuring retrieval Recall@k and judge accuracy (Phase 9).
- Does **not** store raw source documents or student PII — only model inputs/outputs and latency metadata.

## Interfaces

**Inbound:** Python code in `core/llm.py`, `core/embeddings.py`, `core/reranker.py`, and pipeline orchestrators call the Langfuse SDK (`@observe()` decorator or manual span API).

**Outbound:** SDK sends HTTPS batched event payloads to `http://localhost:3000` (self-hosted) or `https://cloud.langfuse.com` (cloud).

**LiteLLM integration:** LiteLLM can forward all model call metadata to Langfuse automatically via `success_callback`:
```python
import litellm
litellm.success_callback = ["langfuse"]
os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
os.environ["LANGFUSE_HOST"] = "http://localhost:3000"
```

**Web UI:** accessible at `http://localhost:3000` for trace browsing, prompt management, and evaluation dashboards.

## Implementation notes

Self-hosted via Docker Compose (one Langfuse container + a dedicated Postgres instance).

```python
# src/asag/core/llm.py — manual trace example (pre-LiteLLM integration)
from langfuse.decorators import observe, langfuse_context

@observe(name="rag_qa")
async def answer_question(question: str, notebook_id: str) -> str:
    chunks = await retrieve(question, notebook_id)      # child span
    langfuse_context.update_current_observation(
        input={"question": question},
        metadata={"chunk_count": len(chunks)},
    )
    answer = await generate(question, chunks)            # child span
    langfuse_context.update_current_observation(output=answer)
    return answer
```

Key config (`docker-compose.yml`): Langfuse service + `langfuse-db` (Postgres 15) + `NEXTAUTH_SECRET` + `SALT`.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Trace storage | Postgres (local) | Langfuse self-hosted uses its own Postgres instance |
| UI port | 3000 | localhost, not public-facing |
| SDK overhead per call | < 5 ms | Async batch sender; non-blocking |
| Cost | $0 | MIT self-hosted |
| Data retention | Unlimited | Until disk fills |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Langfuse container down | SDK `ConnectionError` on batch flush | SDK buffers events in memory; flushes when service recovers (up to `max_retries`) | No production impact — observability data loss only; no functional outage |
| Langfuse Postgres full | `DiskFull` error in Langfuse logs | Increase disk; purge old traces via Langfuse UI | Trace writes stop; SDK silently drops events |
| SDK instrumentation error | Uncaught exception inside `@observe()` decorator | Langfuse SDK catches exceptions and re-raises after recording; ASAG function runs normally | Trace may be incomplete; function completes |
| Eval harness regression | Recall@5 drops below threshold in nightly eval | Alert admin; bisect prompt/retrieval changes via trace comparison | No user-facing impact; used to prevent silent quality regressions |

## Security & data handling

- **PII:** model inputs (prompts with retrieved chunks) may contain educational content. Self-hosted Langfuse keeps data within the ASAG network. Do not send student names or IDs in trace metadata.
- **Authn:** Langfuse UI protected by `NEXTAUTH_SECRET` credential. Rotate regularly; not exposed to the internet.
- **Data residency:** fully on-prem (self-hosted). Migrating to Langfuse Cloud transfers trace data to Langfuse's EU/US servers.
- **API keys:** `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` in `.env`.

## Observability

Langfuse is itself an observability tool. It exposes:
- An internal Postgres database queryable for custom analytics.
- A REST API for programmatic trace retrieval (used by the eval harness).
- No Prometheus endpoint by default (self-hosted v2+).

Monitor the self-hosted instance by watching its Postgres disk usage and Langfuse container CPU/memory in the Docker host's metrics.

## Scaling considerations

- **Self-hosted bottleneck:** Langfuse's Postgres instance becomes the limiting factor at > 1,000 traces/minute. At ASAG's learning scale (< 100 traces/day), this is never reached.
- **Upgrade path:** switching from self-hosted to Langfuse Cloud requires one environment variable change (`LANGFUSE_HOST`). Zero SDK code changes.
- **Retention policy:** implement a periodic `DELETE FROM traces WHERE created_at < NOW() - INTERVAL '90 days'` to control disk usage in production.

## References

- [Langfuse docs](https://langfuse.com/docs)
- [Self-hosting guide](https://langfuse.com/self-hosting)
- [LiteLLM × Langfuse integration](https://langfuse.com/integrations/model-providers/litellm)
