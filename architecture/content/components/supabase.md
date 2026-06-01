---
title: "Supabase"
category: "storage"
icon: "🗄️"
usedInPipeline: ["ingestion", "retrieval", "qa", "assessment", "slides"]
status: "in-use"
current:
  name: "Supabase Cloud (free tier)"
  tier: "free tier"
  pros:
    - "500 MB database + 1 GB storage + 50k MAU — all free"
    - "Postgres native — pgvector, full-text search, and RLS in one place"
    - "Auth included — skip building login from scratch"
  cons:
    - "Single managed provider with soft quotas"
    - "Less control over database tuning than self-hosted Postgres"
prodAlternative:
  name: "AWS RDS (Postgres) + S3 + Cognito / Auth0"
  tier: "managed / paid"
  pros:
    - "Per-service tuning — read replicas, S3 lifecycle policies, SAML SSO"
    - "Enterprise SLAs and regional data residency guarantees"
  why_better: "At school-district scale: separate RDS with read replicas, S3 with lifecycle policies, and Cognito/Auth0 for SSO with SAML. Supabase Pro stays a fine option until ~50k users."
---

# Supabase

## What it is

Supabase is a managed backend platform built on PostgreSQL. It bundles a managed Postgres database, an S3-compatible object storage service, a JWT-based authentication system, and a Realtime pub/sub layer — all under one API and dashboard. ASAG uses Supabase's Postgres (with the pgvector extension) as its primary data store, Supabase Auth for user management and JWT issuance, and Supabase Storage for uploaded source files and generated artefacts. The free tier provides 500 MB database, 1 GB storage, and 50k monthly active users — sufficient for a classroom pilot.

## Responsibilities

- **Postgres database:** store all application data (users, notebooks, chunks, quizzes, attempts, answers, artefacts).
- **Auth:** issue JWTs containing `user_id`, `org_id`, and `role` claims; verified by FastAPI on every request.
- **Storage:** hold uploaded source files (PDF, DOCX, images, code) and generated artefacts (`.pptx`, `.html`). Return signed download URLs scoped to the authenticated user.
- **RLS enforcement:** Postgres row-level security policies run at the database layer, ensuring cross-tenant data isolation even if application code makes an erroneous query.
- Does **not** run application logic — Supabase is a data layer only. All business logic lives in `src/asag/`.

## Interfaces

**Database (psycopg async):** ASAG connects via a psycopg3 connection pool using the `SUPABASE_DB_URL` (direct Postgres connection string). The pool is initialised in `core/db.py`.

**Auth (Supabase client):** the Streamlit UI uses the Supabase JS client to handle OAuth login and receive a JWT. FastAPI verifies the JWT using the Supabase JWT secret.

**Storage (Supabase Python client or signed URL API):**
```python
# Upload a source file and get a signed URL
from supabase import create_client

supabase = create_client(settings.supabase_url, settings.supabase_service_key)
supabase.storage.from_("sources").upload(
    path=f"{org_id}/{source_id}.pdf",
    file=file_bytes,
    file_options={"content-type": "application/pdf"},
)
signed_url = supabase.storage.from_("sources").create_signed_url(
    path=f"{org_id}/{source_id}.pdf", expires_in=3600
)
```

**RLS context (psycopg):** FastAPI sets `SET LOCAL app.user_id = '...'` on each connection before executing queries, activating the RLS policies.

## Implementation notes

```python
# src/asag/core/db.py
import psycopg
from psycopg_pool import AsyncConnectionPool
from asag.config import get_settings

_pool: AsyncConnectionPool | None = None

async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(get_settings().supabase_db_url, min_size=2, max_size=10)
    return _pool

async def set_rls_context(conn, user_id: str, org_id: str) -> None:
    await conn.execute(
        "SELECT set_config('app.user_id', %s, true), set_config('app.org_id', %s, true)",
        (user_id, org_id),
    )
```

Key config:
- `SUPABASE_URL` — REST API base URL
- `SUPABASE_ANON_KEY` — public key for client-side auth
- `SUPABASE_SERVICE_KEY` — admin key (admin scripts only, never in request paths)
- `SUPABASE_DB_URL` — direct Postgres connection string for psycopg

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Free tier DB size | 500 MB | ~62k chunk rows at 8 KB each |
| Free tier storage | 1 GB | Sufficient for ~500 school documents |
| Free tier MAU | 50,000 | Active users per month |
| Connection pool size | 2–10 connections | Per FastAPI worker process |
| Storage signed URL TTL | Configurable | Default 1 hour |
| Postgres version | 17 | pgvector/pgvector:pg17 (local dev) |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Supabase free tier pause (inactive project) | All DB connections fail; HTTP 503 from Supabase API | Reactivate project from dashboard; implement a keep-alive ping | Full outage until reactivated (free tier pauses inactive projects) |
| Auth JWT secret rotation | All FastAPI requests return 401 | Update `SUPABASE_JWT_SECRET` in FastAPI `.env`; redeploy | All users logged out |
| Storage bucket quota exceeded | Upload returns 413 | Delete old artefacts; upgrade to Supabase Pro | Source file uploads fail |
| psycopg pool exhausted | `TooManyConnections` error | Increase `max_size`; add PgBouncer as a connection pooler | Write requests queue; slow requests fail |
| RLS policy error (inadvertent bypass) | Cross-tenant data visible in queries | Audit `pg_policies`; re-enable RLS; roll back erroneous migration | Privacy breach; immediate rollback required |

## Security & data handling

- **Auth:** Supabase Auth issues RS256 JWTs. FastAPI verifies the signature using the public key from Supabase's JWKS endpoint. Token expiry: 1 hour.
- **RLS:** every table has RLS enabled (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`). Policies use `current_setting('app.user_id')` set per-connection by FastAPI.
- **Service-role key:** bypasses RLS — used **only** in `scripts/` for admin operations (seeding, migrations). Never passed to user-facing code paths.
- **Storage:** signed URLs are scoped to the requesting user's `org_id`. Buckets are private (no public access).
- **Encryption:** Supabase Cloud encrypts data at rest (AES-256) and in transit (TLS 1.2+).
- **GDPR:** Supabase Cloud (EU region) is GDPR-compliant. Verify region assignment for school data.

## Observability

- Supabase dashboard shows DB size, storage usage, and connection count in real time.
- `pg_stat_activity` for in-flight queries; `pg_stat_user_tables` for row counts per table.
- Langfuse span `db_query` (Phase 9+) captures query latency and row count.
- Alert: DB size > 400 MB (80% of free tier) → plan upgrade or archival.

## Scaling considerations

- **Free tier ceiling:** 500 MB DB and 1 GB storage are the first limits reached. Upgrade to Supabase Pro ($25/month) for 8 GB DB + 100 GB storage before hitting them.
- **Connection pooling:** Supabase Pro includes PgBouncer (connection pooler), which is critical when running multiple FastAPI workers.
- **Read replicas:** available on Supabase Enterprise for read-heavy workloads (vector search is read-heavy).
- **Production architecture:** at school-district scale, decompose: AWS RDS (Postgres) for the database, S3 for file storage, and Cognito/Auth0 for SAML SSO. Supabase Pro covers the intermediate stage (~50k MAU, multi-class deployments).

## References

- [Supabase docs](https://supabase.com/docs)
- [Supabase RLS guide](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase pricing](https://supabase.com/pricing)
