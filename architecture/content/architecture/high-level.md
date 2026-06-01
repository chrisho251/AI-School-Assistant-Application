---
title: "High-Level Architecture"
---

# High-Level Architecture

> One picture of the whole system. Every box on the diagram links to its own component page.

## Diagram intent

Show — at a single glance — who talks to ASAG, which services do the heavy lifting, where data lives, and how observability wraps everything. The diagram has three horizontal layers: users at the top, application and AI services in the middle, and the data plane at the bottom. Every named box links to its component detail page.

## Layers (top to bottom)

### 1. Users
- **Teacher** — creates notebooks, uploads materials, generates and reviews.
- **Student** — reads, asks, takes quizzes.

### 2. Frontend
- **Streamlit Web UI** — single web app, role-based routing (teacher view / student view / exam view).

### 3. API Gateway
- **FastAPI** — verifies Supabase JWT, extracts `user_id` + `org_id`, applies rate limiting, dispatches to internal services.

### 4. Application services
- **Ingestion Worker** — pulls uploaded files, parses, chunks, embeds, stores.
- **RAG Engine** — hybrid retrieval + reranker + Q&A; shared by chat, quiz, and slide flows.
- **Assessment Engine** — quiz generation, auto-grading (LLM-as-Judge), teacher review.
- **Studio Engine** — slide deck generation via Marp.

### 5. AI services (self-hosted in Docker)
- **TEI / BGE-M3** — text embedding service.
- **TEI / bge-reranker-v2-m3** — reranker service.

### 6. AI services (external SaaS, free tier)
- **Gemini 2.5 Flash** — generator LLM (Q&A, quiz drafting, slide outline).
- **Groq / Llama 3.3 70B** — judge LLM (grading). Different vendor on purpose.
- **LiteLLM** — thin wrapper that lets any service call any model with one interface.

### 7. Data plane (Supabase)
- **Postgres + pgvector** — relational tables, vector index, RLS policies.
- **Supabase Storage** — original uploaded files.
- **Supabase Auth** — user identity + JWT.

### 8. Observability
- **Langfuse (self-host)** — traces every LLM call, prompt versioning, cost tracking.

## Flows shown on the diagram

| Flow | Path |
|---|---|
| Upload | Teacher UI → FastAPI → Storage → enqueue → Ingestion Worker → TEI embed → Postgres |
| Chat / Q&A | Student UI → FastAPI → RAG Engine → (TEI embed query) + (Postgres hybrid search) + (TEI rerank) → Gemini → SSE stream back |
| Quiz generation | Teacher UI → FastAPI → Assessment Engine → RAG Engine retrieve → Gemini structured output → Postgres (draft) |
| Quiz attempt + grading | Student UI → FastAPI → Postgres → on submit → Assessment Engine → Groq judge → Postgres (`auto_score`) → teacher review → finalise |
| Slide generation | Teacher UI → FastAPI → Studio Engine → RAG retrieve → Gemini outline → Marp CLI → Storage (.pptx) |

## Nodes that must be clickable on the diagram

Each of these must link to `/components/<slug>` on the site:

- `streamlit` → `components/streamlit.md`
- `fastapi` → `components/fastapi.md`
- `tei` → `components/tei.md` (covers both embedding + reranker hosting)
- `bge-m3` → `components/bge-m3.md`
- `bge-reranker` → `components/bge-reranker.md`
- `gemini-flash` → `components/gemini-flash.md`
- `groq-llama` → `components/groq-llama.md`
- `litellm` → `components/litellm.md`
- `supabase` → `components/supabase.md` (covers Auth + Storage)
- `pgvector` → `components/pgvector.md`
- `langfuse` → `components/langfuse.md`
- `docling` → `components/docling.md` (lives inside Ingestion Worker)
- `marp` → `components/marp.md` (lives inside Studio Engine)

## Visual notes (for the implementer)

- Group "Application services" with a soft outline so the four boxes read as siblings.
- Place AI services in a separate horizontal band to emphasise they are infrastructure.
- The data plane is a cylinder cluster on the right — pgvector and Storage are children of Supabase.
- Use the pastel palette from `sample-diagrams/`: amber for users, sky for services, rose/violet for AI models, slate for data stores.
- Below the diagram, render a `StageBar` showing the request lifecycle: `Auth → Route → Retrieve → Generate → Persist → Observe`.
