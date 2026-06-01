# ASAG — Project Overview

> **Tagline**: An AI knowledge workspace for classrooms — teachers upload materials, students chat with them, and the system creates and grades quizzes automatically.

## Elevator pitch (for non-tech readers)

Imagine Google NotebookLM, but built specifically for a classroom and with two extra superpowers:

1. **Permission control between teachers and students.** Teachers decide what each class can see.
2. **A full assessment loop.** The same system that helps students learn from the material can also generate tests on it, grade student answers, and let the teacher review every score before it becomes official.

The student never needs to ask "what does this paragraph mean?" to a classmate at midnight — they can ask ASAG, and the answer will only come from the teacher's own materials, with citations back to the source page.

## Who it's for

| User | What they do |
|---|---|
| **Teacher** | Creates a notebook per topic, uploads materials (PDF, Word, images, code), grants access, generates slides and tests, reviews auto-graded scores. |
| **Student** | Joins a notebook, reads, asks questions in natural language with cited answers, takes quizzes in a locked browser, sees feedback after teacher review. |
| **School admin (future)** | Manages organisations, classes, billing. |

## Core principles

1. **Grounded answers only.** Every answer, quiz question, and slide must cite the exact source chunks it came from. The system refuses to answer when the material does not cover the question.
2. **Privacy by default.** Materials are isolated per tenant (school) using Postgres Row-Level Security. Student data never crosses notebook boundaries.
3. **Teacher in the loop on grading.** AI proposes scores; the teacher finalises. No grade is written to the official record without a teacher click.
4. **Anti-bias grading.** The model that generates a quiz is never the same as the model that grades it. This is a documented safeguard against self-preference bias.
5. **Cost-conscious learning build.** The current stack runs on free tiers and self-hosted open-source models. Every component page documents what a production-grade alternative would look like.

## What's in scope vs out of scope

**In scope (v1)**:
- Notebooks with PDF / DOCX / PNG / JPG / .py / .ipynb support
- RAG question answering with citations
- Slide deck generation (export to PPTX)
- Quiz generation (multiple choice, short answer, essay, code)
- Auto-grading with LLM-as-Judge + rubric
- Teacher review and finalisation flow
- Browser-level exam lockdown (fullscreen + tab-switch detection)
- Multi-tenant data isolation (RLS)

**Out of scope (v1)**:
- Podcast / audio overviews
- Native mobile apps
- Real-time collaborative editing
- Video lectures

## Technology summary

| Layer | Choice | Why |
|---|---|---|
| Document parsing | Docling (self-hosted) | 97.9% table accuracy; open source |
| Embeddings + Reranker | BGE-M3 + bge-reranker-v2-m3, served by HuggingFace TEI | Multilingual, self-hostable, no rate limits |
| Vector store | Postgres + pgvector (Supabase) | One database for metadata, vectors, and RLS |
| LLM (generator) | Gemini 2.5 Flash | Free tier 1500 req/day, 1M token context, multimodal |
| LLM (judge) | Groq Llama 3.3 70B | Different vendor → anti-bias; 300+ tokens/sec |
| LLM wrapper | LiteLLM | Single interface, easy to swap providers |
| Slides | Marp CLI | Markdown → PPTX/HTML, free |
| Observability | Langfuse (self-host) | Trace every LLM call |
| Backend | FastAPI | Async-native Python, OpenAPI built-in |
| Frontend | Streamlit | Fastest path to a working UI in Python |

See `components/` for the dedicated page of each item above.
