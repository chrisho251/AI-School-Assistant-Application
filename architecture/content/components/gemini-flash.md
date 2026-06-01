---
title: "Gemini 2.5 Flash"
category: "llm"
icon: "✨"
usedInPipeline: ["ingestion", "qa", "assessment", "slides"]
status: "in-use"
current:
  name: "Gemini 2.5 Flash (free tier)"
  tier: "free tier"
  pros:
    - "1,500 requests per day free — no credit card required"
    - "1M token context window — a 30-page PDF fits without aggressive chunking"
    - "Multimodal natively — handles image captioning in the same API"
    - "Reliable structured JSON output enforcement"
  cons:
    - "Daily quota cap and region restrictions"
    - "Data-use policy: prompts may inform model training"
prodAlternative:
  name: "Anthropic Claude Sonnet 4.6"
  tier: "managed / paid"
  pros:
    - "Higher reasoning quality on long, dense technical material"
    - "Stronger instruction-following and rubric adherence"
    - "Predictable structured output with fewer JSON-parse errors"
  why_better: "Produces noticeably better answers on the kind of academic content schools upload. Reduces teacher overrides on auto-generated quizzes and slides. $3/M input + $15/M output tokens."
---

# Gemini 2.5 Flash

## What it is

Gemini 2.5 Flash is Google's mid-tier large language model, optimised for speed and cost efficiency within the Gemini 2.5 family. It supports a 1-million-token context window, multimodal input (text, image, audio, video), and structured JSON output enforcement via a schema parameter. ASAG uses it as the primary generator model across four pipelines: Q&A generation, quiz drafting, slide outline writing, and image captioning during ingestion. The free tier provides 1,500 requests per day with no credit card required, which is sufficient for a learning build or a classroom pilot.

## Responsibilities

- **Q&A generation:** receive retrieved chunks + user question → produce a cited answer with `[source_id:chunk_id:page]` references.
- **Quiz drafting:** receive chunks + teacher configuration → produce structured `questions[]` JSON conforming to the `questions` table schema.
- **Slide outline writing:** receive top-30 chunks → produce `[{slide_title, bullets[], source_chunk_ids[]}]` JSON.
- **Image captioning (ingestion):** receive embedded image bytes → produce a dense academic description for indexing as a chunk.
- Does **not** grade student answers — that role belongs to the judge model (Groq Llama 3.3 70B) to avoid self-preference bias.

## Interfaces

**Inbound:** `core/llm.py` calls LiteLLM with model string `"gemini/gemini-2.5-flash"`. Caller passes a `messages` list (OpenAI format) and optionally a `response_format` JSON schema.

**Outbound:** HTTPS call to `generativelanguage.googleapis.com`. Requires `GEMINI_API_KEY` environment variable.

**Structured output:** LiteLLM routes the `response_format` parameter to Gemini's JSON schema enforcement. The model returns a conforming JSON string; `core/llm.py` parses it before returning to the caller.

**Streaming:** for Q&A, the model is called with `stream=True`; tokens are forwarded as SSE chunks through the FastAPI route.

## Implementation notes

Called via LiteLLM — callers never import `google-generativeai` directly.

```python
# src/asag/core/llm.py (simplified)
import litellm
from asag.config import get_settings

async def chat(
    messages: list[dict],
    response_format: dict | None = None,
    stream: bool = False,
) -> str | litellm.ModelResponse:
    settings = get_settings()
    return await litellm.acompletion(
        model="gemini/gemini-2.5-flash",
        messages=messages,
        response_format=response_format,
        stream=stream,
        api_key=settings.gemini_api_key,
    )
```

Prompt templates live in `src/asag/rag/prompts/` and `src/asag/assessment/prompts/` as Markdown files — never hardcoded multiline strings.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Free quota | 1,500 req/day | Per Google AI Studio account |
| Context window | 1,000,000 tokens | Full PDF as fallback context |
| Output token limit | 8,192 tokens | Per request |
| Latency (first token) | ~500–2,000 ms | Varies by region and load |
| Streaming | Yes | SSE via LiteLLM |
| Cost (paid) | $0.075 / M input + $0.30 / M output | At time of writing |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Daily quota exhausted (free tier) | HTTP 429 from Gemini API | Switch to Groq Llama 3.3 70B via LiteLLM fallback config; alert admin | All generation routes return fallback model responses |
| Structured output parse failure | `json.JSONDecodeError` after model returns malformed JSON | Retry with stricter schema prompt up to 2 times; raise `GenerationError` | Single quiz/slide generation attempt fails; user sees error message |
| API region unavailability | HTTP 503 from Google endpoint | LiteLLM retry with exponential back-off (3 attempts) | Generation pipeline stalls for ~10 s before error surface |
| Prompt injection in student content | Model follows injected instructions | System prompt hardening (role boundaries, input sanitisation) — see Security section | Model behaviour deviates; Langfuse trace shows unexpected output |

## Security & data handling

- **Data-use policy:** Gemini free tier prompts may be used by Google to improve their models. Do **not** send personally identifiable student data (names, IDs, exam responses) in prompts for free-tier usage. Use the paid API (which has a no-train data policy) for production.
- **Prompt injection:** student-authored content (answers, chat messages) is placed in the `user` role; the `system` role sets hard boundaries. Never interpolate raw student input into the system prompt.
- **API key:** stored in `.env` as `GEMINI_API_KEY`; loaded via `pydantic-settings`. Never committed to git.
- **Data residency:** Gemini API is hosted on Google Cloud; data leaves the ASAG host on every call.

## Observability

- LiteLLM automatically logs `prompt_tokens`, `completion_tokens`, and `cost` per call; these are forwarded to Langfuse (Phase 9+).
- Alert: if Gemini error rate > 5% in a 5-minute window → activate Groq fallback and notify admin.
- Prompt versioning: each prompt template file is tracked in git; Langfuse stores the prompt version hash alongside each trace.

## Scaling considerations

- **Free tier quota is the primary constraint.** At 1,500 req/day, a class of 30 students asking ~5 questions each uses 150 requests — the quota supports ~10 active classes per day before hitting the limit.
- **Paid tier removes quota:** at $0.075/M input tokens, a 1,000-token RAG context + question costs ~$0.0001 per request — effectively free at classroom scale.
- **Multimodal calls cost more:** image captioning during ingestion uses vision tokens (billed at a higher rate on the paid tier).
- **Fallback model:** LiteLLM fallback list: `["gemini/gemini-2.5-flash", "groq/llama-3.3-70b-versatile"]`. Activated automatically on 429 or 503.

## References

- [Gemini API docs](https://ai.google.dev/gemini-api/docs)
- [Free tier limits](https://ai.google.dev/pricing)
- [Structured output guide](https://ai.google.dev/gemini-api/docs/structured-output)
