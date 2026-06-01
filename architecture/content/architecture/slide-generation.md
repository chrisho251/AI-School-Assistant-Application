---
title: "Slide Generation Pipeline"
---

# Slide Generation Pipeline

> Notebook in, `.pptx` out. Same retrieval pipeline as Q&A; the only difference is the prompt and the renderer.

## Why it's a separate pipeline

A slide deck has fundamentally different structural requirements from a chat answer: it needs titled slides, bulleted hierarchy, speaker notes, and an export format PowerPoint and Keynote can open. Mixing this output format into the Q&A chain would require branching logic across prompts and renderers. A dedicated pipeline keeps the prompt schema, Jinja template, and Marp invocation isolated from the Q&A and assessment pipelines.

## Steps

### 1. Broad retrieval
Pull the **top ~30 chunks** that span the notebook (more than Q&A uses, because a deck must cover the whole topic). Standard hybrid + rerank pipeline.

### 2. Outline generation
Call the generator LLM with a structured-output prompt. Schema:

```jsonc
[
  {
    "slide_title": "...",
    "bullets": ["...", "..."],
    "visual_hint": "diagram of pipeline | chart of X | none",
    "source_chunk_ids": ["chunk_uuid_..."]   // grounding rule
  },
  ...
]
```

### 3. Render to Marp markdown
A Jinja template converts the outline into a valid Marp document:

```md
---
marp: true
theme: default
paginate: true
---

# Slide title

- Bullet 1
- Bullet 2

<!-- Notes: ... -->

---
```

Marp markdown is human-readable. The teacher can hand-edit before re-rendering.

### 4. Marp CLI export
A Python `subprocess` calls `@marp-team/marp-cli`:

```bash
marp deck.md -o deck.pptx
marp deck.md -o deck.html
```

Both outputs are uploaded to Supabase Storage and a row is written to `artifacts`.

## Why Marp instead of direct python-pptx?

- Markdown is easier to diff, version, and review than a binary `.pptx`.
- Marp gives both `.pptx` (for editing) and `.html` (for live preview in the UI) from the same source.
- Themes can be swapped without touching the outline logic.

## Components on the diagram

- `gemini-flash` (outline generation)
- Retrieval pipeline (for broad context)
- `marp` (rendering)
- `supabase` Storage (final artefact)

## Failure modes

- LLM returns invalid JSON → retry with a stricter prompt, then fall back to a default 5-slide skeleton.
- Marp CLI not installed on the worker → ingestion worker Docker image bundles Node + `@marp-team/marp-cli`.
- Image hints — v1 skips actual image generation; deck contains a placeholder note for the teacher to insert manually.
