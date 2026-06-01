---
title: "Marp"
category: "infra"
icon: "🖼️"
usedInPipeline: ["slides"]
status: "in-use"
current:
  name: "Marp CLI (@marp-team/marp-cli)"
  tier: "free / open source"
  pros:
    - "Free MIT — runs as a subprocess in the worker container"
    - "Markdown slides are diffable in git and reviewable in PRs"
    - "Same source produces .pptx and .html from one render command"
  cons:
    - "Limited animation support and fewer slide layout options"
prodAlternative:
  name: "python-pptx with custom template engine"
  tier: "free / open source"
  pros:
    - "Pixel-perfect control over PPTX layouts, branding, and master slides"
    - "Supports animations and complex brand theme requirements"
  why_better: "Schools with strict branding requirements (logo placement, font rules, colour palettes) need pixel control that Markdown themes cannot easily provide. python-pptx with a brand-engineered template wins there."
---

# Marp

## What it is

Marp CLI (`@marp-team/marp-cli`) is an open-source Node.js command-line tool that converts Markdown files (with slide separator syntax `---`) into presentation formats: `.pptx`, `.html` (Reveal.js-compatible), or `.pdf`. Themes are defined as CSS files and swappable independently of slide content. ASAG invokes Marp as a subprocess from the slide generation worker — the LLM produces a Jinja-rendered Marp Markdown file, and Marp converts it to `.pptx` and `.html` in a single render call.

## Responsibilities

- Final stage of the slide generation pipeline: receive a Marp Markdown file path → produce `.pptx` and `.html` files.
- Apply the configured Marp theme (CSS) to control visual style.
- Does **not** generate content — the LLM produces the Markdown; Marp only renders it.
- Does **not** upload artefacts — the worker uploads output files to Supabase Storage after Marp exits.

## Interfaces

**Inbound:** `studio/slides.py` calls `marp` via `subprocess.run()`. Input: path to a temporary `.md` file containing the LLM-generated Marp content.

**Outbound:** writes output files to the specified output path. No network calls; purely file I/O.

**Subprocess call:**
```bash
marp deck.md --pptx -o deck.pptx
marp deck.md --html  -o deck.html
```

**Marp Markdown format (first two slides):**
```markdown
---
marp: true
theme: asag-default
---

# Lesson: Binary Trees

- Definition and properties
- Use cases in databases

---

## Traversal Algorithms

- Inorder: Left → Root → Right
- Preorder: Root → Left → Right
```

## Implementation notes

Installed via npm in the worker container: `npm install -g @marp-team/marp-cli`.

```python
# src/asag/studio/slides.py (simplified)
import subprocess
from pathlib import Path
import tempfile

async def render_slides(marp_content: str, artifact_id: str) -> tuple[Path, Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "deck.md"
        pptx_path = Path(tmpdir) / "deck.pptx"
        html_path = Path(tmpdir) / "deck.html"
        md_path.write_text(marp_content, encoding="utf-8")
        subprocess.run(["marp", str(md_path), "--pptx", "-o", str(pptx_path)], check=True)
        subprocess.run(["marp", str(md_path), "--html",  "-o", str(html_path)], check=True)
        return pptx_path, html_path
```

Theme files live in `src/asag/studio/templates/` as `.css` files referenced in the Marp front-matter.

## Operational characteristics

| Metric | Value | Notes |
|---|---|---|
| Render time (20-slide PPTX) | ~2–5 s | CPU; Node.js subprocess startup included |
| Render time (HTML) | ~1–3 s | Faster than PPTX |
| Output size (PPTX) | 100–500 KB | Depends on embedded images |
| Node.js version | 20+ | Required by @marp-team/marp-cli |
| Cost | $0 | MIT |

## Failure modes & recovery

| Mode | Detection | Recovery | Blast radius |
|---|---|---|---|
| Marp not installed in container | `FileNotFoundError` on subprocess call | Add `npm install -g @marp-team/marp-cli` to worker Dockerfile | All slide generation jobs fail at render step |
| LLM produces invalid Marp syntax | Marp exits non-zero; `subprocess.CalledProcessError` | Log offending Markdown; return error to teacher with option to retry | Single slide generation attempt fails |
| PPTX output too large (> 25 MB) | Supabase Storage upload fails | Compress images in Marp Markdown before rendering; or strip embedded images | Upload step fails; teacher sees error |
| Node.js version mismatch | Marp CLI crashes with Node API error | Pin Node version in Dockerfile (`FROM node:20-slim`) | All slide jobs fail |

## Security & data handling

- **Authn:** Marp is a local subprocess — no network exposure. Security boundary is at the FastAPI / worker level.
- **Content injection:** the Marp Markdown content comes from an LLM response seeded by source chunks. Ensure the Jinja template escapes any HTML within slide content to prevent JavaScript injection in the `.html` output (relevant if HTML slides are served directly from the app).
- **File handling:** temporary files are written to `tempfile.TemporaryDirectory()` and automatically deleted on context exit. No intermediate content persists to disk beyond the render call.
- **Artefact storage:** generated `.pptx` and `.html` are uploaded to Supabase Storage with a signed URL scoped to the notebook owner.

## Observability

- Render duration logged per artefact in `artifacts.payload.render_ms`.
- Langfuse span `render_slides` (Phase 9+) captures input token count (Marp Markdown length), render time, and output file sizes.
- Alert: render time > 30 s → likely LLM produced a very large Markdown file or Node.js is under memory pressure.

## Scaling considerations

- **Subprocess startup cost:** each `marp` call starts a Node.js process (~300 ms). For high-throughput slide generation, keep a warm Node.js process using the Marp API directly (avoid subprocess per call).
- **Concurrency:** multiple workers can run `marp` in parallel since it is stateless and file-based.
- **Production alternative:** `python-pptx` avoids the Node.js dependency entirely, but requires significantly more code for layout control. Schools with strict brand templates will need it; general academic use is fine with Marp themes.

## References

- [Marp CLI docs](https://github.com/marp-team/marp-cli)
- [Marp themes guide](https://marpit.marp.app/theme-css)
- [VS Code Marp preview extension](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)
