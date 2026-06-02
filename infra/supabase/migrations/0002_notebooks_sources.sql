-- 0002_notebooks_sources.sql — Notebooks, notebook ACL, sources
-- Depends on: 0001_init.sql

-- Notebooks (linked to class, teacher is implicit via class)
create table if not exists notebooks (
    id uuid primary key default uuid_generate_v4(),
    class_id uuid not null references classes(id) on delete cascade,
    owner_id uuid not null references users(id),
    title text not null,
    subject text,
    description text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index on notebooks(class_id);
create index on notebooks(owner_id);

-- Notebook ACL (fine-grained access control beyond class membership)
-- permission: 'read' | 'edit' | 'admin'
create table if not exists notebook_acl (
    id uuid primary key default uuid_generate_v4(),
    notebook_id uuid not null references notebooks(id) on delete cascade,
    user_id uuid references users(id) on delete cascade,
    class_id uuid references classes(id) on delete cascade,
    permission text not null check (permission in ('read', 'edit', 'admin')),
    created_at timestamptz not null default now(),
    constraint check_acl_user_or_class check ((user_id is not null) != (class_id is not null))
);
create index on notebook_acl(notebook_id);
create index on notebook_acl(user_id);
create index on notebook_acl(class_id);

-- Sources (uploaded documents)
-- type: 'pdf' | 'docx' | 'image' | 'code' (extensible via registry)
-- ingestion_status: 'pending' | 'processing' | 'ready' | 'failed'
create table if not exists sources (
    id uuid primary key default uuid_generate_v4(),
    notebook_id uuid not null references notebooks(id) on delete cascade,
    source_type text not null default 'pdf',
    original_filename text not null,
    storage_url text not null,
    file_size_bytes bigint,
    page_count integer,
    checksum text,
    ingestion_status text not null default 'pending' check (
        ingestion_status in ('pending', 'processing', 'ready', 'failed')
    ),
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (notebook_id, checksum)
);
create index on sources(notebook_id);
create index on sources(ingestion_status);
