-- 0004_assessment.sql — Assessment pipeline (quizzes, Q&A, artifacts)
-- Depends on: 0003_chunks.sql

-- Conversations (RAG Q&A sessions)
create table if not exists conversations (
    id uuid primary key default uuid_generate_v4(),
    notebook_id uuid not null references notebooks(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    title text,
    started_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index on conversations(notebook_id);
create index on conversations(user_id);

-- Messages (chat history with citations)
create table if not exists messages (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    citations jsonb default '[]',
    tokens_used integer,
    created_at timestamptz not null default now()
);
create index on messages(conversation_id);

-- Artifacts (slides, summaries, mindmaps, etc.)
-- kind: 'slide_deck' | 'summary' | 'mindmap' | 'infographic'
-- status: 'generating' | 'ready' | 'failed'
create table if not exists artifacts (
    id uuid primary key default uuid_generate_v4(),
    notebook_id uuid not null references notebooks(id) on delete cascade,
    kind text not null check (
        kind in ('slide_deck', 'summary', 'mindmap', 'infographic', 'outline')
    ),
    title text,
    status text not null default 'generating' check (status in ('generating', 'ready', 'failed')),
    payload jsonb default '{}',
    file_url text,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index on artifacts(notebook_id);
create index on artifacts(kind);
create index on artifacts(status);

-- Quizzes (assessment template, versioning via status)
-- status: 'draft' | 'published' | 'archived'
create table if not exists quizzes (
    id uuid primary key default uuid_generate_v4(),
    notebook_id uuid not null references notebooks(id) on delete cascade,
    created_by uuid not null references users(id),
    title text not null,
    description text,
    time_limit_sec integer,
    proctoring_config jsonb default '{"enabled": false}',
    status text not null default 'draft' check (status in ('draft', 'published', 'archived')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index on quizzes(notebook_id);
create index on quizzes(created_by);
create index on quizzes(status);

-- Questions (quiz items, type-extensible via registry)
-- type: 'mcq' | 'short' | 'essay' | 'code' (POC ships mcq + short)
create table if not exists questions (
    id uuid primary key default uuid_generate_v4(),
    quiz_id uuid not null references quizzes(id) on delete cascade,
    ordinal integer not null,
    type text not null check (type in ('mcq', 'short', 'essay', 'code')),
    stem text not null,
    options jsonb,
    answer jsonb,
    rubric jsonb,
    source_chunk_ids uuid[] default '{}',
    difficulty_level text default 'medium' check (difficulty_level in ('easy', 'medium', 'hard')),
    created_at timestamptz not null default now(),
    unique (quiz_id, ordinal)
);
create index on questions(quiz_id);
create index on questions(type);

-- Attempts (student quiz submissions)
-- status: 'in_progress' | 'submitted' | 'graded' | 'finalized'
create table if not exists attempts (
    id uuid primary key default uuid_generate_v4(),
    quiz_id uuid not null references quizzes(id) on delete cascade,
    student_id uuid not null references users(id) on delete cascade,
    started_at timestamptz not null default now(),
    submitted_at timestamptz,
    proctor_events jsonb default '[]',
    status text not null default 'in_progress' check (
        status in ('in_progress', 'submitted', 'graded', 'finalized')
    ),
    created_at timestamptz not null default now()
);
create index on attempts(quiz_id);
create index on attempts(student_id);
create index on attempts(status);

-- Answers (per-question response in an attempt)
-- auto_score: LLM grader result (nullable if grader returns no score)
-- teacher_score: teacher override (nullable until set)
-- final_score: the committed score (auto_score until teacher override)
create table if not exists answers (
    id uuid primary key default uuid_generate_v4(),
    attempt_id uuid not null references attempts(id) on delete cascade,
    question_id uuid not null references questions(id) on delete cascade,
    response jsonb not null,
    auto_score numeric(5, 2),
    auto_feedback text,
    teacher_score numeric(5, 2),
    teacher_feedback text,
    final_score numeric(5, 2),
    finalized_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (attempt_id, question_id)
);
create index on answers(attempt_id);
create index on answers(question_id);
