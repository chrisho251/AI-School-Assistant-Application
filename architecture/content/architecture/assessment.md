---
title: "Assessment Pipeline"
---

# Assessment Pipeline

> Two sub-pipelines: quiz generation (offline, by the teacher) and auto-grading (online, after a student submits). Both share the rule that no AI-generated artefact is final without a teacher click.

## Sub-pipeline A — Quiz generation

### Inputs
- `notebook_id` and a scope (whole notebook, a chapter, or selected chunks).
- A `QuizConfig`: number of questions per type (MCQ, short, essay, code), difficulty distribution.

### Steps

1. **Retrieve** chunks for the scope using the standard retrieval pipeline.
2. **Generate** structured questions with the generator LLM. The prompt enforces a JSON schema (one row per question, with required fields including `rubric` and `source_chunk_ids`).
3. **Validate**:
   - Each `source_chunk_ids` actually appears in the scope.
   - The answer can be supported by the cited chunks (a second LLM pass, "grounded?").
   - MCQ options are unique and the correct option is real.
   - Difficulty distribution matches `QuizConfig`.
4. **Persist** as `quizzes` + `questions` rows with `status = draft`.
5. **Teacher edits** in the UI, then clicks `Publish` to expose to students.

### Output schema highlights

```jsonc
{
  "type": "mcq" | "short" | "essay" | "code",
  "stem": "Why does Postgres prefer HNSW over IVFFlat for high-dim vectors?",
  "options": ["...", "...", "...", "..."],    // MCQ only
  "answer": { "value": "B", "rationale": "..." },
  "rubric": [ { "criterion": "...", "weight": 0.4 }, ... ],  // short/essay/code
  "source_chunk_ids": ["chunk_uuid_1", "chunk_uuid_2"]
}
```

## Sub-pipeline B — Auto-grading

### Trigger
Student submits an attempt → background grading job spawned per `answer`.

### Routing by question type

| Type | Strategy |
|---|---|
| MCQ, True/False | Deterministic comparison with `answer.value`. No LLM call. |
| Fill-in, numeric | Normalise (lowercase, trim, unit conversion) + regex / exact match. |
| Short answer | **LLM-as-Judge** with the rubric, the reference answer, and the chunks the question was generated from. Returns `{ score, reasoning, matched_rubric_items[] }`. |
| Essay | Same as short, but with a multi-dimensional rubric (content / structure / language) and 0–10 scale. |
| Code (explain / fix) | Optional: run unit tests in a sandbox (e.g. `e2b.dev` free tier or a hardened Docker container) plus an LLM explanation pass. |

### Anti-bias rule
The **judge model must not be the same as the generator model**. Default config: generator = Gemini 2.5 Flash, judge = Groq Llama 3.3 70B. Empirical research from 2026 shows shared-model judging inflates scores by 5–15% on subjective rubrics.

### Persist
- `answers.auto_score`
- `answers.auto_feedback`
- `attempts.status = auto_graded`

### Teacher review loop
- Teacher opens the attempt review page.
- Sees auto_score, auto_feedback, the cited chunks, and an editable input for `teacher_score` + `teacher_feedback`.
- Clicks **Finalise** → `answers.final_score = teacher_score ?? auto_score`, `answers.finalized_at = now()`, `attempts.status = finalized`.
- Only now does the score become visible to the student.

## Components on the diagram

- `gemini-flash` (generator)
- `groq-llama` (judge)
- `litellm` (interface for both)
- `pgvector` + retrieval pipeline (for grounding rubric)
- `langfuse` (traces every grading call for audit)

## Why two separate score columns?

`auto_score` and `final_score` are kept as separate columns (not overwritten in place) so the audit trail survives. If a teacher overrides, the original auto judgement is still there for retrospective evaluation of the grader.
