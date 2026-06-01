---
title: "Student Features"
audience: "student"
---

# Features — Student

> Everything a student can do inside ASAG.

## 1. Browse accessible notebooks

After logging in, students see only the notebooks their teachers have shared with them or with their class. Row-Level Security guarantees a student cannot reach another notebook by guessing URLs.

## 2. Read and search materials

Inside a notebook, students can:

- View the original PDF / DOCX / image / code file.
- Search across all materials using natural language.
- Jump from a search result straight to the page or cell where the content lives.

## 3. Ask grounded questions

The conversational view lets students type a question in natural language and get an answer that:

- Is generated **only** from the notebook's materials. If the materials don't cover the question, the system says so honestly instead of guessing.
- Comes with **inline citations** — every claim points back to a specific chunk, page, or file the teacher uploaded.
- Streams in real time so the answer appears as it is being generated.

Conversations are saved so the student can come back later to revisit a thread.

## 4. Take a quiz in lockdown mode

When the student opens a quiz attempt:

1. The browser switches to **fullscreen** (Fullscreen API).
2. **Tab switches** and **window blur** events are detected and logged.
3. **Copy, paste, and right-click** are disabled.
4. After a configurable number of policy violations, the attempt can auto-submit or be flagged for teacher review.

The student sees a timer, the current question, navigation between questions, and a final submit button. After submit, the system runs auto-grading.

## 5. See feedback after teacher review

Auto-grading happens immediately, but scores stay hidden until the teacher finalises. Once finalised, the student sees:

- The score per question and overall.
- Teacher feedback (which may override the auto feedback).
- Which source chunks were considered relevant — so the student can revisit the material and learn.
