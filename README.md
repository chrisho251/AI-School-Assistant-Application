<div align="center">

# ASAG — AI School Assistant & Grader

**A NotebookLM-style teaching workspace that answers, quizzes, and grades — grounded only in your own class materials.**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Postgres](https://img.shields.io/badge/Postgres-pgvector-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Tests](https://img.shields.io/badge/tests-192_passing-brightgreen)](#-testing)

<img src="assets/screenshots/landing.png" alt="ASAG landing page" width="820">

</div>

---

## Table of contents

- [What is ASAG?](#what-is-asag)
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Architecture](#-architecture)
- [How it works](#-how-it-works)
- [Tech stack](#-tech-stack)
- [Quick start](#-quick-start) — **bring your own API keys**
- [Configuration](#-configuration)
- [Testing](#-testing)
- [Project structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)
- [Acknowledgements](#-acknowledgements)

---

## What is ASAG?

ASAG is an AI assistant for the classroom, built as a self-hostable clone of Google NotebookLM with an assessment layer on top. Teachers upload their own materials (PDFs, images); students ask questions and take quizzes generated **from those materials only**. Every answer, quiz question, and slide is traceable back to the exact source chunk it came from.

Two design rules are enforced end-to-end:

- **🎯 Grounded, not hallucinated** — no answer, quiz, or slide is produced without `source_chunk_ids`. If the materials don't cover a question, ASAG says so.
- **⚖️ Cross-model grading** — short answers are graded by a *different* model vendor (Groq Llama) than the one that generated the quiz (Gemini), to avoid self-preference bias. Teachers always get the final say (`auto_score` → `final_score`).

> **Status:** working proof-of-concept. Full pipeline runs locally end-to-end; 192 automated tests pass (see [Testing](#-testing)).

---

## ✨ Features

| | |
|---|---|
| 📚 **Notebook ingestion** | Upload PDFs and images; Docling parses documents, Gemini Vision captions images. Semantic chunking → BGE-M3 embeddings → pgvector. |
| 🔎 **Hybrid RAG retrieval** | Dense + sparse search, fused with Reciprocal Rank Fusion, re-ranked by `bge-reranker-v2-m3`. Answers stream over SSE with inline `[N]` citations. |
| 📝 **Quiz generation** | Multiple-choice and short-answer (with rubric) questions, each grounded in cited chunks. |
| 🤖 **Auto-grading** | Deterministic MCQ scoring + LLM-as-Judge for short answers, with a teacher review-and-override flow. |
| 🖼️ **Slide generation** | Turns notebook content into Marp slide decks. |
| 🔒 **Exam lockdown** | Browser proctoring (fullscreen + tab-switch / blur / key events) logged to a per-attempt timeline. |
| 🏢 **Multi-tenant by design** | Postgres Row-Level Security isolates every organisation; requests run under the user's JWT, never a superuser. |
| 🔧 **Extensible** | Loaders, chunkers, question types, graders, and storage backends all plug in through registries — add a type, not an `if/elif`. |

---

## 📸 Screenshots

<table>
  <tr>
    <td width="50%"><img src="assets/screenshots/teacher-notebooks.png" alt="Teacher notebooks"><br><sub><b>Teacher</b> — notebooks & sources</sub></td>
    <td width="50%"><img src="assets/screenshots/teacher-quizzes.png" alt="Teacher quizzes"><br><sub><b>Teacher</b> — quiz authoring</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="assets/screenshots/student-chat.png" alt="Student ask & learn"><br><sub><b>Student</b> — ask & learn (cited answers)</sub></td>
    <td width="50%"><img src="assets/screenshots/student-quizzes.png" alt="Student quizzes"><br><sub><b>Student</b> — take a proctored quiz</sub></td>
  </tr>
</table>

---

## 🏗️ Architecture

```mermaid
flowchart TB
    UI["<b>React SPA</b><br/>teacher &amp; student<br/>Vite · TypeScript · Tailwind"]:::client

    subgraph API ["&nbsp;⚙️&nbsp; FastAPI backend &nbsp;"]
        direction TB
        ROUTES["<b>API routers</b><br/>notebooks · sources · chat<br/>quizzes · attempts · proctor"]:::api
        AUTH["<b>Auth &amp; tenancy</b><br/>JWT · Row-Level Security"]:::api
    end

    subgraph SVC ["&nbsp;🧠&nbsp; Domain services &nbsp;"]
        direction LR
        ING["<b>Ingestion</b><br/>Docling · chunking"]:::svc
        RET["<b>RAG retrieval</b><br/>hybrid · RRF · rerank"]:::svc
        ASSESS["<b>Assessment</b><br/>quiz gen · grading"]:::svc
        STUDIO["<b>Studio</b><br/>Marp slides"]:::svc
    end

    subgraph DATA ["&nbsp;🗄️&nbsp; Self-hosted infrastructure &nbsp;"]
        direction LR
        PG[("<b>Postgres</b><br/>pgvector · RLS")]:::data
        TEI["<b>TEI</b><br/>BGE-M3 · reranker"]:::data
        OBJ["<b>Object storage</b>"]:::data
    end

    subgraph AI ["&nbsp;☁️&nbsp; LLM providers — your API keys &nbsp;"]
        direction LR
        GEN["<b>Gemini 2.5 Flash</b><br/>generator"]:::ai
        JUDGE["<b>Groq Llama 3.3 70B</b><br/>judge · cross-model"]:::ai
    end

    UI ==>|"HTTPS · /api"| ROUTES
    ROUTES --> AUTH
    ROUTES ==> SVC
    AUTH -. secures .-> PG
    ING --> TEI & OBJ & PG
    RET --> TEI & PG & GEN
    ASSESS --> GEN & JUDGE & PG
    STUDIO --> GEN & OBJ

    classDef client fill:#e0e7ff,stroke:#6366f1,stroke-width:2px,color:#312e81
    classDef api fill:#cffafe,stroke:#0891b2,stroke-width:2px,color:#164e63
    classDef svc fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#166534
    classDef data fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#713f12
    classDef ai fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#6b21a8

    style API fill:#f8fafc,stroke:#94a3b8,stroke-width:1px,color:#475569
    style SVC fill:#f8fafc,stroke:#94a3b8,stroke-width:1px,color:#475569
    style DATA fill:#f8fafc,stroke:#94a3b8,stroke-width:1px,color:#475569
    style AI fill:#f8fafc,stroke:#94a3b8,stroke-width:1px,color:#475569
```

**Layering rule:** a layer only depends on layers below it. `api/` orchestrates domain services (`ingestion/`, `rag/`, `assessment/`, `studio/`); domain calls `core/` (db, llm, embeddings, storage); `core/` calls external services. Never the reverse.

---

## ⚙️ How it works

**Ingestion**
```
upload → Docling / Gemini Vision → semantic chunks → BGE-M3 (dense + sparse) → pgvector
```

**Retrieval & Q&A**
```
question → hybrid search (dense + sparse) → RRF fusion → bge-reranker → top-k chunks → Gemini → cited answer (SSE)
```

**Assessment**
```
chunks → Gemini quiz gen (MCQ + short) → student attempt → MCQ scored deterministically + short graded by Groq judge → teacher review → final score
```

---

## 🧰 Tech stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · Vite · TypeScript · Tailwind · TanStack Query |
| **Backend** | FastAPI · Pydantic · psycopg (async) |
| **Database** | Postgres 17 + pgvector · Row-Level Security |
| **Embeddings / rerank** | BGE-M3 · bge-reranker-v2-m3, self-hosted via HuggingFace TEI |
| **LLM (generator)** | Google Gemini 2.5 Flash |
| **LLM (judge)** | Groq Llama 3.3 70B — *different vendor, by design* |
| **LLM gateway** | LiteLLM |
| **Documents / slides** | Docling · Marp CLI |
| **Storage** | Supabase Storage (pluggable) |
| **Tooling** | uv · Ruff · mypy (strict) · pytest · Vitest |

---

## 🚀 Quick start

> **You run this with _your own_ free API keys.** ASAG needs a Google Gemini key (generator) and a Groq key (judge). Both have generous free tiers. Nothing in this repo ships with working credentials.

### 1. Prerequisites

- [Docker](https://www.docker.com/) (Postgres + the embedding/reranker services)
- [uv](https://docs.astral.sh/uv/) (Python 3.12+ toolchain)
- [Node 18+](https://nodejs.org/) and [pnpm](https://pnpm.io/) (frontend)
- **Give Docker ≥ 6 GB RAM** — the reranker model is memory-hungry (see [Troubleshooting](#-troubleshooting)).

### 2. Get your API keys (free)

| Key | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio → API keys](https://aistudio.google.com/apikey) |
| `GROQ_API_KEY` | [Groq Console → API keys](https://console.groq.com/keys) |

### 3. Configure the backend

```bash
git clone <your-fork-url> asag && cd asag
cp .env.example .env
```

Open `.env` and paste **your** keys. Then pick a database:

**Option A — bundled Postgres (recommended for local dev).** The `docker compose` stack includes Postgres + pgvector on port 5433. Just set:

```dotenv
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=your-groq-key
SUPABASE_DB_URL=postgresql://asag:asag_local@localhost:5433/asag
```

**Option B — your own Supabase project.** Create a free project at [supabase.com](https://supabase.com/), enable the `vector` extension, and set `SUPABASE_DB_URL` to your **Session pooler** connection string (the IPv4-friendly one). Fill in `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` too if you want cloud file storage.

### 4. Start services & database

```bash
docker compose up -d                        # Postgres + TEI embedder + reranker
uv sync --all-extras                        # Python deps
uv run python scripts/check_connection.py   # expect: Postgres OK + pgvector available
uv run python scripts/apply_migrations.py   # apply all SQL migrations (idempotent)
uv run python scripts/seed_demo.py --with-quiz   # demo org, teacher, students, quiz
```

> First `docker compose up` downloads the BGE-M3 model (~2 GB) — give it a few minutes.

### 5. Run the backend

```bash
uv run python scripts/run_api.py            # API on http://127.0.0.1:8000  (docs at /docs)
```

> **Windows:** always launch via `scripts/run_api.py`, not the raw `uvicorn` CLI — it forces the SelectorEventLoop that async Postgres requires.

### 6. Run the frontend

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev                                    # UI on http://localhost:5173
```

Open **http://localhost:5173** and use the one-click demo login (teacher or student). 🎉

---

## 🔧 Configuration

All settings load from `.env` via `src/asag/config.py`. The most important ones:

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Generator LLM (**required**) | — |
| `GROQ_API_KEY` | Judge LLM (**required**) | — |
| `SUPABASE_DB_URL` | Postgres connection string | — |
| `ASAG_LLM_GENERATOR` | Generator model id | `gemini/gemini-2.5-flash` |
| `ASAG_LLM_JUDGE` | Judge model id (keep a **different vendor**) | `groq/llama-3.3-70b-versatile` |
| `TEI_EMBED_URL` / `TEI_RERANK_URL` | Self-hosted embedding / rerank services | `localhost:8080` / `:8081` |
| `STORAGE_BACKEND` | `supabase` (pluggable) | `supabase` |

See [`.env.example`](.env.example) for the full list.

---

## 🧪 Testing

```bash
uv run pytest tests/unit -q                 # 136 unit tests (mocked I/O)

# Integration tests hit a real Postgres. Point SUPABASE_DB_URL at your dev DB first.
uv run pytest -m integration                # 34 integration tests

# Opt into tests that call real LLM APIs (consumes quota):
ASAG_TEST_LIVE_LLM=1 uv run pytest -m integration

uv run ruff check . && uv run mypy src/asag # lint + strict types

cd frontend && pnpm test && pnpm lint && pnpm build   # 22 frontend tests + build
```

Live-LLM and full-stack tests are opt-in (`ASAG_TEST_LIVE_LLM=1`, `ASAG_TEST_FULL_STACK=1`) so the default run stays fast and free.

---

## 📁 Project structure

```
asag/
├── src/asag/
│   ├── api/            FastAPI routers + auth/RLS dependencies
│   ├── ingestion/      loaders + chunkers + pipeline  (registry-based)
│   ├── rag/            hybrid retriever + Q&A chain
│   ├── assessment/     quiz generation + graders + repository
│   ├── studio/         Marp slide generation
│   ├── core/           db · llm · embeddings · reranker · storage
│   ├── models/         Pydantic schemas (the single contract layer)
│   └── config.py       pydantic-settings
├── frontend/           React + Vite + TS + Tailwind SPA
├── infra/supabase/migrations/   versioned SQL (schema + RLS)
├── scripts/            run_api · apply_migrations · seed_demo · check_connection
├── tests/              unit + integration (real Postgres)
└── docker-compose.yml  Postgres + TEI embedder + reranker
```

---

## 🩹 Troubleshooting

| Symptom | Fix |
|---|---|
| **Reranker container exits (code 137)** | It was OOM-killed while loading the model. Increase Docker's memory to ≥ 6 GB. Retrieval still works without it — the retriever falls back to RRF ranking. |
| **`Psycopg cannot use the 'ProactorEventLoop'` (Windows)** | Start the API with `uv run python scripts/run_api.py`, not the raw `uvicorn` CLI. |
| **`getaddrinfo failed` for a Supabase host** | Direct `db.*.supabase.co` hosts are IPv6-only; use the **Session pooler** connection string, or a paused free project — open the dashboard to resume it. Or use the bundled local Postgres (Option A). |
| **First run is slow** | TEI downloads the BGE-M3 model (~2 GB) on first start; subsequent runs are cached. |

---

## 🗺️ Roadmap

Extensibility hooks are already in place for these (register a type, don't rewrite):

- [ ] Additional loaders: DOCX, source code, Jupyter notebooks
- [ ] Essay & code question types (grader strategy registry)
- [ ] Langfuse observability (tracing decorator stub exists)
- [ ] Production storage backend (R2 / S3 interface exists)
- [ ] Background queue (currently FastAPI `BackgroundTasks`)

---

## 🙏 Acknowledgements

Built as a personal / Master's project. Inspired by [Google NotebookLM](https://notebooklm.google.com/) and the open-source [open-notebook](https://github.com/lfnovo/open-notebook). Powered by [BGE-M3](https://huggingface.co/BAAI/bge-m3), [Docling](https://github.com/DS4SD/docling), [LiteLLM](https://docs.litellm.ai/), and [Marp](https://marp.app/).

---

<div align="center">
<sub>No license file is included yet — add one before sharing publicly if you want to set usage terms.</sub>
</div>
