---
title: "pgvector"
category: "storage"
icon: "🔍"
usedInPipeline: ["ingestion", "retrieval"]
status: "in-use"
current:
  name: "pgvector (in Supabase Postgres)"
  tier: "free / open source"
  pros:
    - "Free PostgreSQL licence — zero vector-DB cost"
    - "One database for metadata, RLS, and vectors — no sync between systems"
    - "Good enough up to ~10M vectors with HNSW"
  cons:
    - "Shares CPU with the OLTP workload"
    - "RAM limits on managed Postgres tiers"
prodAlternative:
  name: "Qdrant (self-host or Cloud)"
  tier: "free / paid (Cloud)"
  pros:
    - "Built for vectors only — faster at scale, richer payload filtering"
    - "Billion-vector support with dedicated hardware"
  why_better: "Above ~10M vectors or with strict p99 latency targets, a dedicated vector database starts to win. Qdrant has excellent price-performance and supports payload filtering identical to what we already do in pgvector."
---

# pgvector

## What it is

pgvector is an open-source Postgres extension (PostgreSQL licence) that adds a `vector` data type and similarity-search operators and indexes to standard Postgres. It supports HNSW (Hierarchical Navigable Small World) and IVFFlat approximate-nearest-neighbour indexes, the `<=>` cosine distance operator, `<->` L2 distance, and `<#>` negative inner product. ASAG stores each document chunk's 1024-dimensional BGE-M3 embedding in a `vector(1024)` column alongside the chunk's text and metadata, enabling hybrid search in a single SQL query without a separate vector database.

## Responsibilities

- Store the dense embedding (`vector(1024)`) for every chunk at ingestion time.
- Store the sparse vector (`jsonb`) for BM25-style sparse retrieval alongside the dense vector.
- Serve approximate-nearest-neighbour queries using the HNSW index during retrieval.
- Enforce multi-tenant isolation via Postgres RLS policies — the same policies that apply to text columns also apply to vector queries.
- Does **not** own chunking, embedding computation, or retrieval orchestration — those live in `ingestion/` and `rag/retriever.py`.

## Interfaces

**Inbound:** `core/db.py` opens an async `psycopg` connection pool. Ingestion pipeline issues `INSERT INTO chunks (embedding, sparse_vector, ...) VALUES (...)`. Retrieval pipeline issues `SELECT ... ORDER BY embedding <=> $query_vec LIMIT 30`.

**SQL interface (dense retrieval):**
```sql
-- HNSW approximate nearest neighbour, filtered by notebook_id
SELECT id, content, metadata,
       embedding <=> $1 AS distance
FROM   chunks
WHERE  notebook_id = $2
ORDER  BY distance
LIMIT  30;
```

**SQL interface (sparse / FTS retrieval):**
```sql
SELECT id, content,
       ts_rank(to_tsvector('english', content), plainto_tsquery($1)) AS rank
FROM   chunks
WHERE  notebook_id = $2
ORDER  BY rank DESC
LIMIT  30;
```

**Index definitions (from migrations):**
- `CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)` — for dense ANN
- `CREATE INDEX ON chunks USING gin (to_tsvector('english', content))` — for FTS sparse

## Implementation notes

Postgres image: `pgvector/pgvector:pg17`.

Migration (`infra/supabase/migrations/0003_chunks.sql`):
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       uuid NOT NULL REFERENCES sources(id),
  notebook_id     uuid NOT NULL REFERENCES notebooks(id),
  ordinal         integer NOT NULL,
  page            integer,
  content         text NOT NULL,
  content_type    text NOT NULL DEFAULT 'text',  -- text|table|image_caption|code
  embedding       vector(1024),
  sparse_vector   jsonb,
  metadata        jsonb DEFAULT '{}',
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX ON chunks USING gin (to_tsvector('english', content));
```

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Vector dimensions | 1024 | float32 (BGE-M3 output) |
| Storage per vector | 4 KB | 1024 × 4 bytes |
| Storage per chunk row | ~5–8 KB | including text, metadata, sparse vector |
| HNSW index build time | < 1 min | for < 100k vectors |
| ANN query latency | < 10 ms | p50, with HNSW, filtered by notebook_id |
| Max vectors before perf degrades | ~10M | with HNSW on managed Postgres |
| Free tier (Supabase) | 500 MB DB | ~62k chunk rows at 8 KB each |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| HNSW index corruption | Query returns wrong results or errors | `REINDEX INDEX CONCURRENTLY`; monitor with `pg_stat_user_indexes` | Retrieval quality degrades until reindex completes |
| Vector dimension mismatch (model swap) | `INSERT` error: `wrong dimension` | Run a migration to drop and recreate the `embedding` column with new dimension; re-embed all chunks | Full re-embedding required; service disrupted during migration |
| Supabase Postgres OOM | Connections drop; DB restarts | Reduce HNSW `ef_search` parameter; add `work_mem` limit per connection | All ASAG services lose DB connectivity until restart (~30 s) |
| Disk quota exceeded (free tier) | `DiskFull` Postgres error | Delete orphaned chunks; archive old notebooks; upgrade to Supabase Pro | No new writes; existing data intact |
| RLS policy misconfiguration | Users see cross-tenant chunks | Audit `pg_policies`; correct and re-enable RLS | Privacy breach; rollback policy immediately |

## Security & data handling

- **RLS:** every table in ASAG has RLS enabled. The `chunks` table policy restricts all operations to `notebook_id` values accessible by the current `app.user_id` claim. See `infra/supabase/migrations/0005_rls.sql`.
- **Service-role bypass:** the Supabase service-role key bypasses RLS. It is used **only** in admin scripts — never in request-handling code paths.
- **Encryption at rest:** Supabase Postgres is encrypted at rest (AES-256) on the managed tier. Self-hosted Postgres: filesystem encryption is the operator's responsibility.
- **PII:** chunk `content` fields contain educational document text, potentially including student names from teacher-uploaded materials. Access is RLS-controlled.

## Observability

- `pg_stat_user_indexes` tracks HNSW index usage and size.
- Retrieval query latency measured via `EXPLAIN ANALYZE` during performance testing; target: p50 < 10 ms, p95 < 50 ms for HNSW queries on `notebook_id`-filtered sets.
- Langfuse span `vector_search` (Phase 9+) captures `chunk_count_returned`, `query_latency_ms`.
- Alert: retrieval latency p95 > 200 ms → check HNSW index health and Postgres memory.

## Scaling considerations

- **HNSW is RAM-bound:** the index is loaded into memory. Supabase's free-tier Postgres has limited RAM (512 MB); the HNSW index for 50k vectors (~200 MB) may compete with other query memory.
- **Vertical first:** upgrade Supabase to a dedicated instance (more RAM, faster IOPS) before switching to a separate vector DB.
- **Horizontal:** pgvector does not shard natively. Partition the `chunks` table by `notebook_id` for parallel scans at large scale.
- **Above ~10M vectors:** migrate to a dedicated vector database (Qdrant, Pinecone). The retriever abstraction in `rag/retriever.py` isolates this change to one module.

## References

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [HNSW paper](https://arxiv.org/abs/1603.09320)
- [Supabase × pgvector tutorial](https://supabase.com/docs/guides/database/extensions/pgvector)
