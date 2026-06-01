---
title: "Groq — Llama 3.3 70B"
category: "llm"
icon: "⚡"
usedInPipeline: ["assessment"]
status: "in-use"
current:
  name: "Groq — Llama 3.3 70B (free tier)"
  tier: "free tier"
  pros:
    - "14,400 requests per day free for developers"
    - "300+ tokens/sec — grading 30 answers finishes in seconds"
    - "Open weights — self-hostable if Groq ever disappears"
  cons:
    - "Daily quota cap"
    - "Fewer reasoning-chain features than frontier closed models"
prodAlternative:
  name: "Anthropic Claude Opus 4.6"
  tier: "managed / paid"
  pros:
    - "Highest reasoning quality available"
    - "Strongest adherence to multi-criterion rubrics"
    - "Less likely to be tricked by confident-sounding wrong answers"
  why_better: "For high-stakes grading, reasoning quality matters most. Claude Opus 4.6 follows complex rubrics more consistently. ~$15/M input + $75/M output — expensive at scale, but justified for official grades."
---

# Groq — Llama 3.3 70B

## What it is

Groq is a chip company that designed custom Language Processing Units (LPUs) optimised for high-throughput LLM inference. Llama 3.3 70B is Meta's open-weight 70-billion-parameter instruction-following model. Running on Groq's LPU hardware, it generates 300+ tokens per second — several times faster than GPU-based inference. ASAG uses it exclusively as the **judge model** for auto-grading open-ended student answers. Choosing a judge model from a different vendor than the generator (Gemini) is an intentional anti-bias design decision: research from 2026 shows that using the same model for generation and evaluation inflates scores by 5–15% on subjective rubrics.

## Responsibilities

- **Auto-grading judge:** receive a student answer, the rubric JSON, and the source chunks as evidence → return `{score, reasoning, matched_rubric_items[]}`.
- Applied only to short-answer, essay, and code-explanation question types. MCQ is graded deterministically.
- Called from `assessment/grader.py` for each answer in an attempt.
- Does **not** generate quiz questions or student-facing content — separation is enforced by architecture, not convention.

## Interfaces

**Inbound:** `core/llm.py` calls LiteLLM with model string `"groq/llama-3.3-70b-versatile"`. Caller passes a grading prompt (with rubric, student answer, and reference evidence) and a `response_format` JSON schema.

**Outbound:** HTTPS call to `api.groq.com/openai/v1/chat/completions` (OpenAI-compatible endpoint). Requires `GROQ_API_KEY` environment variable.

**Response schema:**
```json
{
  "score": 3,
  "max_score": 4,
  "reasoning": "Student correctly identified X but missed Y.",
  "matched_rubric_items": ["item_1", "item_3"]
}
```

## Implementation notes

Groq exposes an OpenAI-compatible API; LiteLLM routes to it with no custom adapter.

```python
# src/asag/assessment/grader.py (simplified)
from asag.core.llm import chat
from asag.models.grading import GradeResult

GRADING_PROMPT_PATH = "src/asag/assessment/prompts/judge.md"

async def grade_answer(
    question: dict, student_answer: str, evidence_chunks: list[str]
) -> GradeResult:
    prompt = load_prompt(GRADING_PROMPT_PATH).format(
        rubric=question["rubric"],
        answer=student_answer,
        evidence="\n\n".join(evidence_chunks),
    )
    raw = await chat(
        model_override="groq/llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format=GradeResult.model_json_schema(),
    )
    return GradeResult.model_validate_json(raw)
```

Key config: `GROQ_API_KEY` in `.env`. Model identifier: `llama-3.3-70b-versatile` (Groq's hosted name).

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Free quota | 14,400 req/day | Developer tier, Llama models |
| Token throughput | 300+ tokens/s | On Groq LPU hardware |
| Grading latency (1 answer) | ~1–3 s | Includes network round-trip |
| Grading latency (30 answers) | ~30–90 s | Sequential; parallelisable |
| Cost (paid) | $0.05 / M input + $0.10 / M output | At time of writing |
| Context window | 128k tokens | Sufficient for full rubric + evidence |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Daily quota exhausted | HTTP 429 from Groq API | Log error; mark attempt `grading_failed`; teacher can trigger re-grade manually | All grading halts until next UTC midnight or quota reset |
| Malformed JSON response | `json.JSONDecodeError` in `GradeResult.model_validate_json()` | Retry with explicit JSON enforcement prompt; max 2 retries | Single answer grade fails; stored as `auto_score = null` for teacher review |
| Groq API outage | `httpx.ConnectError` or HTTP 503 | Retry with exponential back-off (3 attempts); fall back to a secondary judge (Claude Haiku via LiteLLM fallback) | Grading delayed; teacher notified via status field |
| Prompt injection in student answer | Model follows student-embedded instructions | Wrap student input in XML tags with `<student_answer>` marker; system prompt instructs model to ignore content outside rubric task | Score integrity compromised; Langfuse trace allows post-hoc audit |

## Security & data handling

- **Data-use policy:** Groq's paid tier has a no-training data policy. Free tier: assume student content may be logged. Use paid tier for production with real student grades.
- **PII in grading prompts:** student answer text passes through Groq's API. On free tier, avoid sending student names or IDs in the prompt — use opaque `answer_id` references.
- **API key:** `GROQ_API_KEY` in `.env`; loaded via `pydantic-settings`. Never committed to git.
- **Anti-bias:** Groq/Llama is the judge; Gemini is the generator. This pairing must not be reversed without a documented rationale — see `docs/adr/adr-007-anti-bias.md`.

## Observability

- Langfuse span `grade_answer` with attributes: `question_id`, `attempt_id`, `score`, `model`, `latency_ms`, `total_tokens` (Phase 9+).
- Alert: grading error rate > 5% in any 30-minute window → notify admin; suspend attempt auto-submission.
- Aggregate metric: mean auto_score vs teacher_score deviation per quiz, tracked in the eval harness (Phase 9).

## Scaling considerations

- **14,400 req/day** supports grading ~480 attempts of 30 questions each — sufficient for a classroom pilot.
- **Parallelise grading:** answers within a single attempt are independent; grade them concurrently with `asyncio.gather()`. This reduces grading time from `n × 3 s` to `~3 s` total (bounded by Groq's rate limit per minute).
- **Production volume:** at district scale, the paid Groq tier or a dedicated GPU cluster running Llama 3.3 70B (e.g., on Modal) removes the quota ceiling.
- **Swap cost vs quality:** Claude Opus 4.6 as judge significantly improves rubric adherence for essay grading; the LiteLLM model string change requires one line of config.

## References

- [Groq API docs](https://console.groq.com/docs/)
- [Llama 3.3 model card](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct)
- [Anti-bias in LLM-as-Judge research](https://arxiv.org/abs/2408.09235)
