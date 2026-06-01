# Content — Source of Truth

> All architecture site pages (`architecture/site/src/pages/**`) are rendered from these files.
> **Never hardcode facts in MDX**: import or copy from here. If you find a fact missing, add it here first.

## Files

| Path | Used by site page |
|---|---|
| `overview.md` | `/` (Hero + intro section) |
| `features/teacher.md` | `/features#teacher` |
| `features/student.md` | `/features#student` |
| `architecture/high-level.md` | `/diagrams/high-level` |
| `architecture/ingestion.md` | `/diagrams/ingestion` |
| `architecture/retrieval.md` | `/diagrams/retrieval` |
| `architecture/assessment.md` | `/diagrams/assessment` |
| `architecture/slide-generation.md` | `/diagrams/slide-generation` |
| `architecture/data-model.md` | Referenced by all diagrams |
| `components/<name>.md` | `/components/<name>` |

## Writing rules

1. **English only**. Audience is international.
2. **Plain-language first**, technical detail second. Open every section with a metaphor or one-sentence summary anyone can follow.
3. **Single source of truth**. A fact lives in exactly one file. Cross-link with relative paths.
4. **Stable IDs**. Use kebab-case slugs that match the page URL.
5. **No marketing tone**. Honest about trade-offs (e.g. "chosen because it has a free tier; production would use X").
6. **Cite reading material** at the bottom of each file when relevant.

## Component file structure (mandatory)

Every file in `components/` must have these H2 sections in this order:

```
# <Display name>

> One-line summary

## What it is (for non-tech readers)
## Role in ASAG
## How it works (high level)
## Why we picked it for the learning version
## Production alternative
## Further reading
```
