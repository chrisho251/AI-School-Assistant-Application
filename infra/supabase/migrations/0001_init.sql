-- 0001_init.sql — Multi-tenant foundation
-- Run after: enable extension `pgvector` and (if Supabase) `uuid-ossp`.

create extension if not exists "uuid-ossp";
create extension if not exists vector;

-- Organizations (tenant)
create table if not exists organizations (
    id uuid primary key default uuid_generate_v4(),
    name text not null,
    slug text unique not null,
    created_at timestamptz not null default now()
);

-- Users (linked với Supabase auth.users)
create table if not exists users (
    id uuid primary key,                 -- match auth.users.id
    org_id uuid not null references organizations(id) on delete cascade,
    email text not null,
    full_name text,
    role text not null check (role in ('admin', 'teacher', 'student')),
    created_at timestamptz not null default now(),
    unique (org_id, email)
);
create index on users(org_id);

-- Classes
create table if not exists classes (
    id uuid primary key default uuid_generate_v4(),
    org_id uuid not null references organizations(id) on delete cascade,
    name text not null,
    teacher_id uuid not null references users(id),
    created_at timestamptz not null default now()
);
create index on classes(org_id);

create table if not exists class_members (
    class_id uuid not null references classes(id) on delete cascade,
    student_id uuid not null references users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    primary key (class_id, student_id)
);

-- TODO D05: notebooks, sources, chunks
-- TODO D06: quizzes, questions, attempts, answers, artifacts
-- TODO D07: RLS policies
