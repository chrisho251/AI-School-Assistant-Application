---
title: "Data Model"
---

# Data Model

> Postgres schema, multi-tenant from day one, RLS enforced at the database level.

## Tables

```
organizations   (id, name, slug)
users           (id, org_id, email, role: admin|teacher|student)
classes         (id, org_id, name, teacher_id)
class_members   (class_id, student_id)

notebooks       (id, owner_id, class_id, title, subject)
notebook_acl    (notebook_id, user_id|class_id, permission: read|edit)

sources         (id, notebook_id, type, storage_url,
                 original_filename, page_count, ingestion_status, checksum)
chunks          (id, source_id, notebook_id, ordinal, page, content,
                 content_type: text|table|image_caption|code,
                 embedding vector(1024),
                 sparse_vector jsonb,
                 metadata jsonb)

conversations   (id, notebook_id, user_id, started_at)
messages        (id, conversation_id, role, content, citations jsonb, tokens)

artifacts       (id, notebook_id, kind: slide_deck|summary|mindmap,
                 status, payload jsonb, file_url)

quizzes         (id, notebook_id, title, created_by, time_limit_sec,
                 proctoring_config jsonb, status: draft|published|closed)
questions       (id, quiz_id, ordinal, type, stem, options, answer,
                 rubric jsonb, source_chunk_ids uuid[])
attempts        (id, quiz_id, student_id, started_at, submitted_at,
                 proctor_events jsonb, status)
answers         (id, attempt_id, question_id, response jsonb,
                 auto_score numeric, auto_feedback text,
                 teacher_score numeric, teacher_feedback text,
                 final_score numeric, finalized_at)
```

## Indexes worth noting

- `chunks.embedding` — HNSW (cosine).
- `chunks.sparse_vector` — GIN.
- `chunks.notebook_id` — btree (every retrieval query filters on this).
- `notebook_acl (user_id)` and `(class_id)` — btree (RLS policies use these).

## Row-Level Security in one line

Every "user data" table has a policy: a user can `SELECT` only rows whose `notebook_id` (or `org_id`) is reachable through their `users.org_id`, `class_members`, or `notebook_acl`.

The application connects with a per-request JWT so Postgres knows who is asking. The retriever does **not** add `WHERE user_id = …` in application code — RLS does that at the database level, which is much harder to bypass.

## Why two score columns

`auto_score` and `final_score` are intentionally kept separate (not overwritten). This preserves the audit trail and lets us later evaluate how often teachers had to override the grader — that's how we improve rubrics and prompts.

## Why `source_chunk_ids` on questions

It is the *grounding contract*. A question without source citations is rejected during validation. This is the single biggest anti-hallucination safeguard in the assessment pipeline.
