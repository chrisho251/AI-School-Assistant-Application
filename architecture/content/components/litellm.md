---
title: "LiteLLM"
category: "infra"
icon: "🔌"
usedInPipeline: ["qa", "assessment", "slides"]
status: "in-use"
current:
  name: "LiteLLM (in-process library)"
  tier: "free / open source"
  pros:
    - "Free MIT — no infra, lives in the same Python process"
    - "Swap providers by string config — no code change to switch Gemini to Claude"
    - "First-class Langfuse integration for tracing"
  cons:
    - "Each app instance carries its own provider clients"
    - "No centralised key management across services"
prodAlternative:
  name: "LiteLLM Proxy (sidecar process)"
  tier: "free / self-hosted"
  pros:
    - "Centralised API key rotation without redeploying applications"
    - "Per-team budget enforcement and A/B model routing"
  why_better: "In a multi-tenant SaaS, the proxy lets ops rotate keys and enforce budgets without redeploying applications. Adds ~10–50 ms per call — acceptable at most scales."
---

# LiteLLM

## What it is

LiteLLM is an open-source Python library (MIT licence, `>= 1.50`) that provides a single unified function signature for calling any LLM provider — OpenAI, Anthropic, Google Gemini, Groq, Cohere, Ollama, and more. Internally it translates the standard `messages` list (OpenAI format) into each provider's native API format and normalises the response back. ASAG uses LiteLLM as the exclusive point of interaction with LLMs, so that provider swaps (e.g. Gemini free → Claude paid) require only a config string change, not a code rewrite.

## Responsibilities

- Provide `core/llm.py` with a single `chat()` / `stream_chat()` async function callable by all pipeline modules.
- Route each call to the correct provider based on the `model` string (e.g. `"gemini/gemini-2.5-flash"`, `"groq/llama-3.3-70b-versatile"`).
- Enforce structured output (`response_format` parameter) across providers that support it.
- Implement automatic retries with exponential back-off on transient errors (429, 503).
- Forward per-call metadata (`prompt_tokens`, `completion_tokens`, `cost`) to the Langfuse callback.
- Does **not** manage API keys, user auth, or token budgets — those are caller responsibilities.

## Interfaces

**Inbound:** any ASAG module that needs an LLM call imports `core/llm.py`. Payload: standard `messages` list + optional `model_override`, `response_format`, `stream`.

**Outbound:** HTTP/S to the provider endpoint (Google, Groq, Anthropic, etc.). Provider-specific authentication is injected from environment variables.

**Public surface (`core/llm.py`):**
```python
async def chat(
    messages: list[dict],
    model_override: str | None = None,
    response_format: dict | None = None,
    stream: bool = False,
) -> str | AsyncIterator[str]: ...
```

The `model_override` parameter lets the assessment engine specify `"groq/llama-3.3-70b-versatile"` (judge) while the default model remains Gemini (generator).

## Implementation notes

```python
# src/asag/core/llm.py
import litellm
from asag.config import get_settings

litellm.success_callback = ["langfuse"]  # auto-forward to Langfuse

async def chat(
    messages: list[dict],
    model_override: str | None = None,
    response_format: dict | None = None,
    stream: bool = False,
) -> str:
    settings = get_settings()
    model = model_override or settings.default_llm_model
    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        response_format=response_format,
        stream=stream,
        num_retries=3,
        timeout=120,
    )
    return resp.choices[0].message.content
```

Key config (in `.env`):
- `DEFAULT_LLM_MODEL=gemini/gemini-2.5-flash`
- `GEMINI_API_KEY=...`
- `GROQ_API_KEY=...`
- `LANGFUSE_SECRET_KEY=...` / `LANGFUSE_PUBLIC_KEY=...` / `LANGFUSE_HOST=http://localhost:3000`

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Library overhead | < 10 ms | Per-call, in-process routing |
| Retry policy | 3 attempts, exponential back-off | Default `num_retries=3` |
| Timeout | 120 s | For non-streaming calls |
| Cost | $0 | MIT library; provider costs are separate |
| Fallback support | Yes | `fallbacks=[{"model": "..."}]` param |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Provider returns 429 (rate limit) | `litellm.RateLimitError` | LiteLLM retries with back-off; if all retries fail, caller receives the exception | Single request fails; FastAPI returns HTTP 503 to Streamlit |
| Provider API key invalid | `litellm.AuthenticationError` on first call | Alert via Langfuse; update `GEMINI_API_KEY` in `.env` and restart service | All LLM calls fail until key is refreshed |
| Structured output parse failure | `json.JSONDecodeError` in caller | Caller retries with a more explicit prompt schema; LiteLLM does not handle this automatically | Single generation attempt fails |
| LiteLLM library version incompatibility | Import error or `AttributeError` at startup | Pin `litellm==1.x.y` in `pyproject.toml` | Service fails to start; caught in CI |

## Security & data handling

- **API keys:** each provider key is read from environment variables via `pydantic-settings`. Never hard-coded or logged.
- **PII in prompts:** LiteLLM forwards the `messages` list verbatim to the provider. ASAG is responsible for ensuring PII guidelines are met before calling `chat()`.
- **Logging:** LiteLLM can be configured to redact message content in logs. Set `litellm.log_raw_request_response = False` in production.
- **No data stored in-library:** LiteLLM is stateless — it does not persist any prompt or response content.

## Observability

- `litellm.success_callback = ["langfuse"]` automatically creates a Langfuse span for every call, capturing model, token counts, and latency.
- `litellm.failure_callback = ["langfuse"]` captures errors similarly.
- Per-call cost is calculated using LiteLLM's built-in price table and forwarded to Langfuse as `cost_usd`.
- Alert: total LLM spend > $X per day (configurable in Langfuse budget alerts).

## Scaling considerations

- **In-process library** means each FastAPI worker carries its own HTTP client pool for provider connections. At high concurrency (> 50 simultaneous LLM calls), connection pool limits on the provider side become the bottleneck.
- **Proxy mode:** run LiteLLM as a sidecar proxy with `litellm --model gemini/... --port 4000`. All workers share one HTTP connection pool and one API key pool. Adds ~10–50 ms per call. Enables per-team budget enforcement without redeployment.
- **Provider diversification:** adding a second Gemini API key (different Google account) effectively doubles the daily free quota — configure both as `router` entries in LiteLLM.

## References

- [LiteLLM docs](https://docs.litellm.ai/)
- [LiteLLM Proxy guide](https://docs.litellm.ai/docs/simple_proxy)
