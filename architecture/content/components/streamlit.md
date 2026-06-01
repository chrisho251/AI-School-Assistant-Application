---
title: "Streamlit"
category: "ui"
icon: "🖥️"
usedInPipeline: ["qa", "assessment"]
status: "in-use"
current:
  name: "Streamlit"
  tier: "free / open source"
  pros:
    - "Pure Python — same language and mental model as the rest of ASAG"
    - "Working chat page in under 50 lines of code"
    - "Free and deployable on Streamlit Community Cloud"
  cons:
    - "Every interaction re-runs the full script — awkward for complex UIs"
    - "Clunky JS escape hatch for custom components like lockdown mode"
prodAlternative:
  name: "Next.js 15 (App Router) + shadcn/ui"
  tier: "free / open source"
  pros:
    - "Pixel-perfect control, mobile-first, accessible components out of the box"
    - "Real-time without server round-trips (React Server Components + WebSockets)"
    - "SEO-friendly and production-grade for SaaS"
  why_better: "Streamlit's re-run model is a UX wall for drag-and-drop, real-time collaboration, and sophisticated forms. A SaaS targeting hundreds of classrooms eventually needs a proper SPA."
---

# Streamlit

## What it is

Streamlit (`>= 1.39`) is a Python web framework that converts a Python script into a multi-page web application. Each page is a `.py` file; Streamlit re-executes it top-to-bottom on every user interaction and diffed-renders the changes. State between reruns is managed via `st.session_state`. Custom HTML/JavaScript components can be injected using `st.components.v1.html()`, which is how ASAG implements browser-based exam lockdown. Streamlit serves its own static assets and runs on port 8501.

## Responsibilities

- Implement the multi-page UI: login → role dispatch (teacher / student) → feature pages.
- **Teacher pages:** notebook CRUD, file upload, quiz draft editor, attempt review and grade finalisation.
- **Student pages:** notebook browser, chat interface (SSE stream from FastAPI), quiz attempt UI.
- **Exam page:** embeds the browser lockdown custom component (fullscreen enforcement, tab-switch detection, proctor event logging).
- Communicate with FastAPI via HTTPS for all business operations — never touches Postgres or LLMs directly.

## Interfaces

**Inbound (user browser):** HTTP GET to `http://localhost:8501`. Streamlit serves the WebSocket connection for live updates.

**Outbound (to FastAPI):** `httpx` async calls and an SSE client for the chat stream. All calls include the Supabase JWT in the `Authorization: Bearer <token>` header.

**Auth handoff:** Supabase JS client in the browser handles the OAuth flow; on success, the JWT is stored in `st.session_state["access_token"]` and attached to every FastAPI call.

**Custom component interface (exam lockdown):**
```python
# ui/components/lockdown.py
import streamlit.components.v1 as components

def render_lockdown_wrapper(attempt_id: str) -> None:
    components.html(
        f"""<script>
        document.addEventListener('visibilitychange', () => {{
            if (document.hidden) logViolation('{attempt_id}', 'tab_switch');
        }});
        document.addEventListener('fullscreenchange', () => {{
            if (!document.fullscreenElement) logViolation('{attempt_id}', 'exit_fullscreen');
        }});
        </script>""",
        height=0,
    )
```

## Implementation notes

```python
# ui/app.py — multi-page entry point
import streamlit as st

st.set_page_config(page_title="ASAG", layout="wide")

if "access_token" not in st.session_state:
    from ui.pages.login import render_login
    render_login()
    st.stop()

role = st.session_state["role"]
if role == "teacher":
    pg = st.navigation(["Notebooks", "Quizzes", "Review"])
else:
    pg = st.navigation(["Notebooks", "Chat", "Exam"])
pg.run()
```

Run: `uvicorn`-free; `streamlit run ui/app.py --server.port 8501`.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Port | 8501 | Default Streamlit |
| Startup time | ~3–5 s | Cold start including import time |
| Concurrency model | Per-user session thread | Each browser session gets a Python thread |
| Memory per session | ~50–100 MB | Depends on state size |
| SSE streaming | Supported | Via `st.write_stream()` (Streamlit 1.31+) |
| Cost | $0 | Streamlit Community Cloud free tier |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Streamlit rerun loop (infinite re-execution) | CPU spikes; browser appears to reload repeatedly | Add `st.stop()` guards; review `session_state` mutation | Single user session hangs; others unaffected |
| Custom component JS blocked by browser CSP | Lockdown component renders blank | Serve component from same origin; add required CSP headers to Streamlit `config.toml` | Exam lockdown non-functional for affected browser |
| FastAPI unavailable | `httpx.ConnectError` in page handler | Catch and show `st.error("Service unavailable")` | All pages that call FastAPI show error; auth (handled locally) still works |
| `st.session_state` key access on first load | `KeyError` | Always use `.get()` with defaults; initialise keys in `on_load` callback | Page crashes until session is reset |
| File upload > 25 MB | Streamlit silently rejects the upload | Set `server.maxUploadSize = 25` in `config.toml`; show clear error message | Teacher cannot upload large files |

## Security & data handling

- **Authn:** Supabase JWT stored in `st.session_state` — memory-only, not persisted to disk or cookies. Session ends on browser close.
- **Authz:** FastAPI enforces RBAC server-side. The Streamlit UI applies a best-effort client-side role check to avoid rendering teacher-only UI for students, but the API is the enforcement point.
- **Exam integrity:** the browser lockdown component uses Page Visibility API and Fullscreen API events. These are soft signals — a determined student with another device can circumvent them. The system is positioned as a deterrent and audit trail, not a secure examination platform.
- **XSS:** Streamlit renders user content through `st.markdown()` with `unsafe_allow_html=False` by default. Never enable `unsafe_allow_html` for student-provided content.

## Observability

- Streamlit's built-in metrics endpoint: `http://localhost:8501/_stcore/health` for liveness.
- Session count and memory usage monitored via the host's Docker stats.
- FastAPI access logs (logged by uvicorn) provide the authoritative record of all API calls from Streamlit.
- Alert: Streamlit process memory > 1 GB → likely session state accumulation; restart service.

## Scaling considerations

- **Thread-per-session model** limits concurrency. At > 50 simultaneous users, Streamlit's memory footprint (50–100 MB/session) reaches several GB. Run multiple Streamlit processes behind a sticky-session load balancer.
- **Stateless pages** are preferable: pass only IDs in `st.session_state`, fetch data on each rerun from FastAPI. Avoids large in-memory state.
- **Production replacement:** Next.js 15 (App Router) + Supabase client SDK + Tailwind is the natural successor. The FastAPI backend is unchanged; only the UI layer is replaced.

## References

- [Streamlit docs](https://docs.streamlit.io/)
- [Streamlit Components API](https://docs.streamlit.io/develop/concepts/custom-components)
- [Why Streamlit vs Gradio vs Dash](https://blog.streamlit.io/streamlit-vs-gradio-vs-dash/)
