---
title: "FastAPI"
category: "api"
icon: "🚀"
usedInPipeline: ["ingestion", "qa", "assessment", "slides"]
status: "in-use"
current:
  name: "FastAPI (single VM / Fly.io)"
  tier: "free / self-hosted"
  pros:
    - "Idiomatic Python — same language and Pydantic models as the rest of ASAG"
    - "OpenAPI docs auto-generated at /docs — no extra documentation work"
    - "Async-native — high concurrency for I/O-heavy LLM calls and DB queries"
  cons:
    - "Single server is a single point of failure"
prodAlternative:
  name: "FastAPI + Kong API Gateway + Kubernetes"
  tier: "managed / paid"
  pros:
    - "Per-route rate limits, WAF, and blue/green deploys"
    - "Multi-region autoscaling with no application code changes"
  why_better: "FastAPI itself stays. What changes in production is what runs around it: managed load balancing, an API gateway for rate limiting, and autoscaling. The FastAPI code needs no rewrite."
---

# FastAPI

## What it is

FastAPI is a modern Python web framework built on Starlette (ASGI) and Pydantic. It provides automatic OpenAPI schema generation from type annotations, native async/await support, and request validation via Pydantic models. ASAG uses FastAPI as the single HTTP gateway between the Streamlit UI and the core AI pipeline services. All business logic, auth verification, and orchestration flows through this layer. The framework version constraint is `>= 0.115`.

## Responsibilities

- Verify the Supabase JWT on every inbound request and extract `user_id`, `org_id`, and `role` claims.
- Route requests to the appropriate engine: ingestion enqueue, RAG Q&A (SSE stream), quiz CRUD, attempt submit, slide generation trigger.
- Enforce role-based access control: teachers write; students read.
- Set the Postgres RLS context (`set_config('app.user_id', ...)`) on each request so database queries automatically respect row-level security.
- Return typed, validated responses using Pydantic models shared with `src/asag/models/`.
- Serve the OpenAPI documentation at `/docs`.

## Interfaces

**Inbound (from Streamlit UI):**
- `POST /api/v1/sources` — upload a document; enqueue ingestion job
- `GET /api/v1/chat/{notebook_id}` — SSE stream; streams tokens from the RAG Q&A chain
- `POST /api/v1/quizzes` — create a quiz draft
- `POST /api/v1/attempts/{attempt_id}/submit` — submit a student attempt
- `GET /api/v1/artifacts/{artifact_id}` — download a generated slide deck

**Outbound:**
- `psycopg` async pool → Supabase Postgres (all DB queries)
- Inngest client → enqueue background ingestion / grading jobs
- LiteLLM → LLM calls (via `core/llm.py`)
- TEI HTTP → embedding / rerank calls (forwarded to `core/embeddings.py`)

**Authentication:** Supabase JWT verified with `python-jose` or the Supabase client library. Unverified requests return HTTP 401.

## Implementation notes

```python
# src/asag/api/main.py (simplified)
from fastapi import FastAPI, Depends
from asag.api.middleware import verify_jwt, set_rls_context

app = FastAPI(title="ASAG API", version="1.0")

@app.post("/api/v1/sources")
async def upload_source(
    file: UploadFile,
    claims: dict = Depends(verify_jwt),
    db = Depends(get_db),
):
    await set_rls_context(db, claims["sub"], claims["org_id"])
    source_id = await create_source(db, claims["notebook_id"], file)
    await enqueue_ingestion(source_id)
    return {"source_id": str(source_id)}
```

Key dependencies: `fastapi >= 0.115`, `uvicorn[standard]`, `sse-starlette` (for SSE streaming), `python-multipart` (for file uploads).

Server invocation: `uvicorn asag.api.main:app --host 0.0.0.0 --port 8000 --workers 4`.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Port | 8000 | default uvicorn |
| Workers | 4 (prod) / 1 (dev) | `--workers` flag |
| Request timeout | 120 s | SSE streams excluded |
| Concurrency model | asyncio | no threading; one event loop per worker |
| Cost | $0 (self-host) | Fly.io free tier: 256 MB RAM, shared CPU |

> _p50/p95 latency per route to be measured with `scripts/benchmark_api.py` — not yet captured._

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Worker crash (OOM, unhandled exception) | uvicorn auto-restarts worker; 503 briefly | Fly.io / Kubernetes health probe restarts pod | Single worker cycle; other workers serve normally |
| JWT secret rotation | All requests return 401 | Redeploy with new secret; rotate Supabase JWT secret in lockstep | All users logged out simultaneously |
| Database pool exhausted | `psycopg.OperationalError: connection pool full` | Increase pool size; add read replica for read-heavy routes | Write requests queue; long-running requests fail |
| SSE stream abandoned by client | `asyncio.CancelledError` in generator | Generator catches cancellation and closes DB cursor | No data leak; minor memory spike until GC |
| Ingestion queue unavailable (Inngest down) | `InngestError` on enqueue | Return 202 with `status: queued_failed`; UI shows retry button | File upload succeeds; ingestion deferred |

## Security & data handling

- **Authn:** every route uses `Depends(verify_jwt)` — no unauthenticated routes except `GET /health`.
- **Authz (RBAC):** role extracted from JWT claim; teachers-only routes raise HTTP 403 for student tokens.
- **RLS:** `set_rls_context` sets `app.user_id` and `app.org_id` on the Postgres connection before any query, activating row-level security policies. Service-role key is never used for user-initiated requests.
- **PII:** API access logs are sanitised — request bodies are not logged. `user_id` is logged for audit; content is not.
- **CORS:** `allow_origins` restricted to the Streamlit domain; not wildcard.

## Observability

- Structured JSON logs via Python `logging` module; forwarded to stdout for collection by Docker / Fly.io log drains.
- Langfuse trace created at route entry (Phase 9+); spans for DB, LiteLLM, and TEI calls nest inside it.
- Prometheus middleware: `starlette-prometheus` for request count, latency histograms, and error rates per route.
- Alert: `5xx error rate > 1%` for 2 consecutive minutes → PagerDuty (Phase 9 runbook).

## Scaling considerations

- **Vertical first:** increase uvicorn `--workers` to match CPU cores. Async I/O means FastAPI is rarely CPU-bound; it is almost always waiting on DB or LLM.
- **Horizontal:** stateless — deploy N identical pods behind a load balancer. Session state lives in Supabase, not in FastAPI memory.
- **SSE streams hold connections:** long-lived SSE connections (chat) tie up a worker's event loop slot. Use a dedicated worker pool or separate SSE service if SSE connections > 100 concurrent.
- **Production infrastructure:** FastAPI itself needs no rewrite. Adding an API gateway (Kong, AWS API Gateway) provides per-route rate limiting, WAF, and canary routing without touching application code.

## References

- [FastAPI docs](https://fastapi.tiangolo.com/)
- [Async SQL with psycopg + FastAPI](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [SSE in FastAPI](https://github.com/sysid/sse-starlette)
