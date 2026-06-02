-- 0003_chunks.sql — Chunks with embeddings (dense + sparse) and indexes
-- Depends on: 0002_notebooks_sources.sql and vector extension

-- Chunks (semantic text units from sources, indexed for hybrid retrieval)
-- content_type: 'text' | 'table' | 'image_caption' | 'code'
create table if not exists chunks (
    id uuid primary key default uuid_generate_v4(),
    source_id uuid not null references sources(id) on delete cascade,
    notebook_id uuid not null references notebooks(id) on delete cascade,
    ordinal integer not null,
    page_number integer,
    content_type text not null default 'text' check (
        content_type in ('text', 'table', 'image_caption', 'code')
    ),
    content text not null,
    embedding vector(1024),
    sparse_vector jsonb,
    metadata jsonb default '{}',
    created_at timestamptz not null default now(),
    unique (source_id, ordinal)
);
create index on chunks(source_id);
create index on chunks(notebook_id);
create index on chunks(content_type);

-- HNSW index for dense vector search (cosine distance, m=16, ef_construction=64)
create index on chunks using hnsw (embedding vector_cosine_ops) with (m=16, ef_construction=64);

-- GIN index for sparse vector (JSONB) queries for BM25-style search
create index on chunks using gin (sparse_vector jsonb_ops);
