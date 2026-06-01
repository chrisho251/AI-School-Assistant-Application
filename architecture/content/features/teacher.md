---
title: "Teacher Features"
audience: "teacher"
---

# Features — Teacher

> Everything a teacher can do inside ASAG.

## 1. Create a topic notebook

Each subject or unit gets its own notebook. A notebook is the privacy boundary: anything uploaded into it is only visible to students explicitly granted access.

- Create as many notebooks as needed.
- Reuse a notebook across classes by sharing access rather than duplicating content.

## 2. Upload teaching materials

Supported formats:

- **Documents**: PDF, DOCX
- **Images**: PNG, JPG (a vision model writes an academic caption used for retrieval)
- **Code**: `.py`, `.ipynb` (parsed at function / cell level)

The system runs an asynchronous ingestion pipeline (see `architecture/ingestion.md`) so the teacher can keep working while parsing, chunking, and embedding finish in the background.

## 3. Control student access

Per notebook the teacher can:

- Grant access to an entire class or individual students.
- Set read-only or edit permissions.
- Revoke access at any time — Row-Level Security in the database enforces it immediately.

## 4. Generate a lecture slide deck

One click takes the notebook through this flow:

1. Retrieve the top ~30 relevant chunks across the notebook.
2. Ask the generator LLM for a structured slide outline (titles, bullets, visual hints, source citations).
3. Render to Marp markdown.
4. Export to `.pptx` and `.html`.

The teacher can edit the markdown before re-exporting, or download the PPTX and edit in PowerPoint / Keynote.

## 5. Generate a quiz from a chosen scope

The teacher picks:

- **Scope**: whole notebook, a chapter, or specific chunks.
- **Question mix**: how many multiple choice, short answer, essay, code questions.
- **Difficulty distribution**.

Each generated question is grounded to specific source chunks (anti-hallucination rule) and has a rubric attached for the grader. The quiz is saved as a **draft** so the teacher can edit before publishing.

## 6. Review and finalise scores

After students submit, the system auto-grades:

- Multiple choice / fill-in → deterministic match.
- Short answer / essay → LLM-as-Judge using the rubric, scored against reference + retrieved evidence.
- Code → optionally executed in a sandbox plus an LLM explanation check.

The teacher sees a per-attempt review screen with:

- Auto score and rationale.
- The source chunks the grader used.
- Inline override for both score and feedback.
- A single **Finalise** button that writes the official grade.

Until finalise is pressed, the score is never visible to the student.

## 7. View an exam timeline

For every attempt the system logs proctor events: when the student left fullscreen, switched tabs, or pasted text. The teacher can see this timeline before deciding to accept or void the attempt.
