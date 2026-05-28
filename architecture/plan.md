# ASAG Architecture Site — Build Plan

> **Audience**: Claude Code (AI coding agent) thực thi từng step.
> **Style**: mỗi step có **Goal**, **Tasks**, **Files to create/modify**, **Output verify**.
> **Prerequisites**: Node 20+, pnpm installed (`npm i -g pnpm`), repo đã `git init`.
> **Total**: 6 phase, ~30 step. Có thể chạy 1 phát hoặc chia ngày.

---

## Tổng quan các phase

| Phase | Nội dung | Số step |
|---|---|---|
| **0** | Setup Astro + Tailwind + folder structure | 4 |
| **1** | Shared components & layouts (Hero, DiagramFrame, Mermaid wrapper, ComponentLayout, ProsConsTable) | 5 |
| **2** | Landing page (`/`) + Features page (`/features`) | 4 |
| **3** | High-level architecture diagram (hand-craft SVG, clickable) | 4 |
| **4** | Sub-pipeline diagrams (ingestion, retrieval, assessment, slides) | 4 |
| **5** | Component detail pages (13 files MDX) | 6 |
| **6** | Polish, mobile responsive, deploy GitHub Pages | 3 |

---

## Phase 0 — Setup

### Step 0.1 — Init Astro project
**Goal**: scaffold project Astro 5 với TypeScript trong `architecture/site/`.

**Tasks**:
1. `cd architecture && pnpm create astro@latest site -- --template minimal --typescript strict --no-install --no-git --yes`
2. `cd site && pnpm install`
3. Verify `pnpm dev` chạy lên localhost:4321.

**Files**: toàn bộ `architecture/site/` được tạo.

**Verify**: `curl -s localhost:4321 | grep -i astro` ra HTML có chữ Astro.

---

### Step 0.2 — Add Tailwind + MDX integrations
**Goal**: enable Tailwind v4 + MDX.

**Tasks**:
1. `pnpm astro add tailwind --yes`
2. `pnpm astro add mdx --yes`
3. Tạo `src/styles/global.css` với:
   ```css
   @import "tailwindcss";
   :root { color-scheme: light; }
   body { @apply font-sans antialiased; }
   .bg-asag-gradient {
     background-image: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #3b82f6 100%);
   }
   ```
4. Import `global.css` trong `BaseLayout.astro` (Step 1.1).

**Files**: `astro.config.mjs` (updated), `src/styles/global.css` (new).

**Verify**: tạo trang test với `<div class="bg-blue-500 p-4">test</div>`, mở localhost:4321 thấy box xanh.

---

### Step 0.3 — Install Mermaid
**Goal**: cài Mermaid để render diagram client-side.

**Tasks**:
1. `pnpm add mermaid`
2. (Không cần Astro integration — sẽ wrap thủ công trong component ở Step 1.4)

**Files**: `package.json` (updated).

**Verify**: `pnpm list mermaid` ra version >=11.

---

### Step 0.4 — Folder skeleton + config
**Goal**: tạo full folder structure theo CLAUDE.md section 3.

**Tasks**:
1. Tạo các folder rỗng: `src/layouts/`, `src/components/`, `src/pages/diagrams/`, `src/pages/components/`, `src/content/`, `public/diagrams/`
2. Thêm `.gitkeep` cho mỗi folder rỗng
3. Tạo `src/content/config.ts` skeleton:
   ```ts
   import { defineCollection, z } from "astro:content";
   // Placeholder — content collections sẽ define ở phase sau nếu cần
   export const collections = {};
   ```
4. Tạo `astro.config.mjs` setup:
   - `site: "https://<user>.github.io"` (placeholder, sẽ điền lúc deploy)
   - `base: "/asag-architecture"` (hoặc tên repo nếu deploy GH Pages)
   - `integrations: [tailwind(), mdx()]`

**Files**: full skeleton + `src/content/config.ts`.

**Verify**: `tree src -L 2` khớp với section 3 trong CLAUDE.md.

---

## Phase 1 — Shared components & layouts

### Step 1.1 — `BaseLayout.astro`
**Goal**: layout chung có `<head>` + nav + footer.

**Tasks**:
- Props: `title`, `description`
- `<head>`: meta tags (viewport, og:title, og:description), import global.css
- Body: `<Nav />` ở top, `<slot />` ở giữa, footer đơn giản ("Built by Chris · ASAG Master project · 2026")
- Sử dụng class `min-h-screen bg-slate-50`

**Files**: `src/layouts/BaseLayout.astro`.

**Verify**: tạo test page dùng layout này, view source thấy meta + nav.

---

### Step 1.2 — `Nav.astro`
**Goal**: nav bar với links Home / Features / Diagrams / GitHub.

**Tasks**:
- Top bar `bg-white shadow-sm sticky top-0 z-50`
- Logo bên trái: "ASAG" + tagline ngắn
- Links bên phải: `/`, `/features`, `/diagrams`, link external tới GitHub repo của Chris (placeholder URL)
- Mobile: hamburger (giai đoạn polish, phase 6)

**Files**: `src/components/Nav.astro`.

**Verify**: render trong BaseLayout, click link `/features` ra 404 (chưa có) — đúng hành vi giai đoạn này.

---

### Step 1.3 — `DiagramFrame.astro`
**Goal**: khung "card trắng trên gradient" — wrapper bắt buộc cho mọi diagram, match phong cách sample.

**Tasks**:
- Props: `title?`, `subtitle?`
- Cấu trúc:
  ```astro
  <section class="bg-asag-gradient p-8 md:p-12 rounded-3xl">
    <div class="bg-white rounded-2xl p-6 md:p-10 shadow-2xl">
      {title && <h3 class="text-xl font-semibold text-slate-800 mb-1">{title}</h3>}
      {subtitle && <p class="text-sm text-slate-500 mb-6">{subtitle}</p>}
      <div class="overflow-x-auto">
        <slot />
      </div>
    </div>
  </section>
  ```

**Files**: `src/components/DiagramFrame.astro`.

**Verify**: dùng trong test page với 1 box bên trong, kiểm tra nền gradient + card trắng.

---

### Step 1.4 — `Mermaid.astro`
**Goal**: wrapper render Mermaid client-side, hỗ trợ click.

**Tasks**:
- Props: `code` (string definition Mermaid)
- Render `<pre class="mermaid">{code}</pre>` trong slot
- Script `is:inline type="module"` import mermaid từ CDN hoặc bundle:
  ```js
  import mermaid from "mermaid";
  mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "default" });
  mermaid.run({ querySelector: ".mermaid" });
  ```
- `securityLevel: "loose"` BẮT BUỘC để click hoạt động

**Files**: `src/components/Mermaid.astro`.

**Verify**: tạo test page với Mermaid flowchart 3 node có `click NodeA href "/foo"`, mở browser click ra navigate đúng.

---

### Step 1.5 — `ComponentLayout.astro` + `ProsConsTable.astro`
**Goal**: layout chuẩn cho mỗi trang component MDX + bảng so sánh free-tier vs production.

**Tasks**:
1. `ComponentLayout.astro`:
   - Frontmatter props: `title`, `category`, `icon`, `usedInPipeline`
   - Hero nhỏ: icon + title + category badge + "Dùng ở: <pipeline list>" với link tới `/diagrams/<pipeline>`
   - `<slot />` cho body MDX
   - Sidebar phải (desktop): "Related components" — TODO link sau
2. `ProsConsTable.astro`:
   - Props: `current` `{name, tier, pros[], cons[]}`, `alternative` `{name, tier, pros[], why_better}`
   - Render bảng 2 cột "Hiện tại (học tập)" vs "Production alternative"
   - Cuối bảng: 1 callout box giải thích `why_better`

**Files**: `src/layouts/ComponentLayout.astro`, `src/components/ProsConsTable.astro`.

**Verify**: tạo `src/pages/components/_test.mdx` dùng layout + table, mở `/components/_test` thấy đầy đủ.

---

## Phase 2 — Landing page + Features

### Step 2.1 — Hero section
**Goal**: hero trên trang chủ — tagline + CTA.

**Tasks**:
- Tạo `src/components/Hero.astro`:
  - Background `bg-asag-gradient text-white py-24`
  - H1 lớn: "ASAG — AI School Assistant & Grader"
  - Sub: 2-3 câu tiếng Việt dễ hiểu cho người không tech ("Hệ thống AI giúp giáo viên tạo notebook tài liệu, sinh đề thi và tự chấm; học sinh hỏi đáp trực tiếp với tài liệu lớp học.")
  - 2 CTA: "Xem kiến trúc" → `/diagrams/high-level`, "Tính năng" → `/features`

**Files**: `src/components/Hero.astro`, `src/pages/index.astro` (dùng Hero).

**Verify**: `/` render đầy đủ hero.

---

### Step 2.2 — Feature cards section (trên landing)
**Goal**: grid 3-4 feature card chính ngay dưới Hero.

**Tasks**:
- Tạo `src/components/FeatureCard.astro` (props: `icon`, `title`, `description`, `href`)
- 4 card:
  1. "Notebook tài liệu thông minh" — upload PDF/DOCX/code, hỏi đáp tức thì → `/features#notebook`
  2. "Tạo slide bài giảng tự động" — sinh PPTX từ tài liệu → `/features#slides`
  3. "Tạo đề thi + tự chấm" — quiz generation + LLM-as-Judge → `/features#assessment`
  4. "Chế độ thi an toàn" — browser lockdown khi học sinh làm bài → `/features#exam`
- Add vào `index.astro` dưới Hero

**Files**: `src/components/FeatureCard.astro`, update `src/pages/index.astro`.

**Verify**: `/` có Hero + 4 card responsive.

---

### Step 2.3 — High-level diagram preview trên landing
**Goal**: thumbnail diagram high-level + nút "Xem chi tiết".

**Tasks**:
- Section sau feature cards
- Hiển thị thumbnail static (PNG) hoặc Mermaid compact của high-level architecture
- Nút "Xem chi tiết → /diagrams/high-level"
- Kèm 1 đoạn giải thích 3 câu

**Files**: update `src/pages/index.astro`.

**Verify**: thumbnail diagram render, click nút điều hướng đúng (trang chưa có là OK ở step này).

---

### Step 2.4 — Features page (`/features`)
**Goal**: trang liệt kê đầy đủ tính năng theo persona (giáo viên / học sinh).

**Tasks**:
- 2 section lớn: "Dành cho giáo viên" và "Dành cho học sinh"
- Mỗi section liệt kê 4-6 tính năng (đọc từ `../requirement.md` của project mẹ)
- Mỗi tính năng: icon + tiêu đề + 2-3 dòng mô tả + (nếu liên quan diagram) link tới diagram đó
- Anchor IDs khớp với link từ FeatureCard (`#notebook`, `#slides`, `#assessment`, `#exam`)

**Files**: `src/pages/features.astro`.

**Verify**: `/features#assessment` scroll đúng section.

---

## Phase 3 — High-level architecture diagram

### Step 3.1 — Design SVG inline cho high-level
**Goal**: 1 file Astro `/diagrams/high-level` chứa SVG hand-craft, match phong cách sample.

**Tasks**:
- Tạo `src/pages/diagrams/high-level.astro`
- Bọc trong `<DiagramFrame title="High-level Architecture">`
- SVG `viewBox="0 0 1200 700"`, các node:
  - **Người dùng** (trái): icon "Giáo viên", "Học sinh"
  - **Frontend layer**: box "Streamlit UI"
  - **API layer**: box "FastAPI Gateway"
  - **3 service**: "Ingestion Worker", "RAG Engine", "Assessment Engine"
  - **AI services**: box "TEI BGE-M3", "TEI Reranker", "Gemini 2.5 Flash", "Groq Llama 3.3"
  - **Data layer**: cylinder "Supabase Postgres + pgvector", "Supabase Storage"
  - **Observability**: box "Langfuse"
- Mỗi node clickable wrap trong `<a href="/components/<name>">`
- Arrows: dùng SVG `<path>` với `marker-end="url(#arrow)"`, định nghĩa `<defs><marker id="arrow">` 1 lần
- Color palette pastel theo CLAUDE.md section 4

**Files**: `src/pages/diagrams/high-level.astro`.

**Verify**: mở `/diagrams/high-level`, click bất kỳ node nào → chuyển trang `/components/<name>` (chưa có thì 404 — OK).

---

### Step 3.2 — Stage progress bar (dưới diagram)
**Goal**: thanh stage giống sample (Extraction → Chunking → Embedding → Vector Ingestion).

**Tasks**:
- Component reuse `src/components/StageBar.astro` (props: `stages: string[]`)
- Render dãy pill nối bằng arrow `>` giữa các pill
- Dùng dưới mỗi diagram lớn để tóm tắt flow

**Files**: `src/components/StageBar.astro`, update `high-level.astro`.

**Verify**: StageBar render đẹp ở desktop + mobile.

---

### Step 3.3 — Legend + caption
**Goal**: chú thích màu sắc + ngữ nghĩa node types.

**Tasks**:
- Component `src/components/DiagramLegend.astro`
- Bảng nhỏ: màu vàng = "Người dùng / UI", màu xanh = "Service tính toán", màu hồng = "AI model", màu xám = "Storage"
- Place dưới mỗi diagram

**Files**: `src/components/DiagramLegend.astro`, update `high-level.astro`.

**Verify**: legend hiển thị đúng.

---

### Step 3.4 — Diagrams index (`/diagrams`)
**Goal**: trang index liệt kê 5 diagram với thumbnail + mô tả.

**Tasks**:
- `src/pages/diagrams/index.astro`
- Grid 5 thẻ: High-level, Ingestion, Retrieval, Assessment, Slide gen
- Mỗi thẻ: tên + 1 câu mô tả + nút "Mở"

**Files**: `src/pages/diagrams/index.astro`.

**Verify**: `/diagrams` show 5 thẻ.

---

## Phase 4 — Sub-pipeline diagrams

Mỗi step làm 1 diagram dùng Mermaid (đủ cho flow 5-10 node).

### Step 4.1 — Ingestion pipeline
**Goal**: `/diagrams/ingestion` — flow 4 stage (Persist → Parse → Chunk → Embed → Index).

**Tasks**:
- Mermaid flowchart LR có click syntax cho mỗi node
- Wrap trong `<DiagramFrame>`
- Dưới diagram: 4 section ngắn giải thích từng stage (tham khảo nội dung mình đã giải thích trong chat về Pipeline 1)
- Link reference tới Docling, BGE-M3, pgvector pages

**Files**: `src/pages/diagrams/ingestion.astro`.

**Verify**: render đúng + click node mở component page.

---

### Step 4.2 — Retrieval pipeline
**Goal**: `/diagrams/retrieval` — hybrid search + RRF + reranker.

**Tasks**:
- Mermaid diagram phân nhánh: query → embed → [dense | sparse] → RRF → reranker → top-k
- Click syntax cho BGE-M3, pgvector, bge-reranker
- Section dưới: giải thích RRF (công thức) + cross-encoder vs bi-encoder (ngôn ngữ đời thường)

**Files**: `src/pages/diagrams/retrieval.astro`.

**Verify**: click nodes works.

---

### Step 4.3 — Assessment pipeline (quiz gen + grading)
**Goal**: `/diagrams/assessment` — flow quiz generation + auto-grading + teacher review.

**Tasks**:
- 2 sub-diagram (cùng 1 trang, 2 DiagramFrame):
  1. Quiz generation: chunks → Gemini structured output → validation → draft questions
  2. Auto-grading: student answer → router theo loại câu (MCQ deterministic / LLM-as-Judge for short/essay/code) → auto_score → teacher review → final_score
- Nhấn mạnh nguyên tắc anti-bias: judge model ≠ generator model

**Files**: `src/pages/diagrams/assessment.astro`.

**Verify**: 2 diagram render + nội dung khớp `../proposal.md` section 6.5.

---

### Step 4.4 — Slide generation pipeline
**Goal**: `/diagrams/slide-generation` — flow notebook → outline → Marp markdown → PPTX.

**Tasks**:
- Mermaid flow: retrieval top-30 → LLM outline JSON → Jinja Marp template → marp-cli → PPTX + HTML
- Click syntax cho Gemini, Marp

**Files**: `src/pages/diagrams/slide-generation.astro`.

**Verify**: ok.

---

## Phase 5 — Component detail pages

Mỗi step làm 2-3 component pages (MDX). Theo template ở CLAUDE.md section 6.

### Step 5.1 — Storage + DB layer
- `supabase.mdx`: Supabase nói chung
- `pgvector.mdx`: extension vector trong Postgres

**Production alternative gợi ý**:
- Supabase → AWS RDS + Auth0 + S3 (production-grade, đắt hơn)
- pgvector → Qdrant / Pinecone (dedicated vector DB, scale tốt hơn ở >10M vectors)

---

### Step 5.2 — Parsing + Ingestion
- `docling.mdx`
- (Bonus optional) `tiktoken.mdx`

**Production alternative**:
- Docling → LlamaParse (managed, faster but $/page); hoặc Reducto, Mistral OCR

---

### Step 5.3 — Embedding + Reranker
- `bge-m3.mdx`
- `tei.mdx` (HuggingFace Text Embeddings Inference)
- `bge-reranker.mdx`

**Production alternative**:
- BGE-M3 self-host → Cohere Embed v4 (managed, multimodal native)
- bge-reranker → Cohere Rerank 3.5 hoặc Voyage rerank-2

---

### Step 5.4 — LLM layer
- `gemini-flash.mdx` (generator)
- `groq-llama.mdx` (judge — anti-bias)
- `litellm.mdx` (wrapper)

**Production alternative**:
- Gemini 2.5 Flash → Anthropic Claude Sonnet 4.6 (chất lượng cao hơn, structured output ổn, tốn $)
- Groq Llama 3.3 70B → Anthropic Opus 4.6 (judge tốt hơn, latency cao hơn, đắt)

---

### Step 5.5 — Observability + UI + API
- `langfuse.mdx`
- `fastapi.mdx`
- `streamlit.mdx`
- `marp.mdx`

**Production alternative**:
- Langfuse self-host → Langfuse Cloud / Datadog LLM Observability
- Streamlit → Next.js + shadcn/ui (production UX, mobile-first)
- Marp → python-pptx + custom theme engine

---

### Step 5.6 — Cross-link tất cả component pages
**Goal**: mỗi page có "Related components" sidebar.

**Tasks**:
- Update `ComponentLayout.astro`: tự động render related dựa trên frontmatter `usedInPipeline`
- Link 2 chiều: trên diagram pipeline cũng list component pages liên quan

**Files**: update `src/layouts/ComponentLayout.astro` + tất cả MDX pages.

**Verify**: mở `/components/bge-m3` thấy "Related: tei, bge-reranker, pgvector" link đúng.

---

## Phase 6 — Polish + Deploy

### Step 6.1 — Mobile responsive
**Goal**: site dùng tốt trên mobile.

**Tasks**:
- Nav: hamburger menu (Tailwind + `<details>` element, không cần JS framework)
- Diagram: scroll ngang trong DiagramFrame (đã có `overflow-x-auto`)
- Font + spacing: kiểm tra trên `360px width`
- Test pages chính: index, features, diagrams/high-level, components/bge-m3

**Files**: update `Nav.astro`, kiểm tra CSS các page.

**Verify**: Chrome DevTools mobile mode, tất cả page không bị vỡ.

---

### Step 6.2 — SEO + meta
**Goal**: meta tags + sitemap + Open Graph cho share link đẹp.

**Tasks**:
- `pnpm astro add sitemap --yes`
- Update `BaseLayout.astro`: og:image, og:url đầy đủ
- Tạo 1 ảnh `public/og-image.png` (1200×630)

**Files**: `astro.config.mjs`, `BaseLayout.astro`, `public/og-image.png`.

**Verify**: `pnpm build` xong, mở `dist/sitemap-index.xml` có đầy đủ URL.

---

### Step 6.3 — Deploy GitHub Pages
**Goal**: deploy auto qua GitHub Actions.

**Tasks**:
- Tạo `.github/workflows/deploy-architecture.yml`:
  - Trigger: push lên `main` branch, filter `architecture/site/**`
  - Steps: checkout → setup-node → pnpm install → pnpm build (in `architecture/site/`) → upload `dist/` → deploy to `gh-pages` branch
- Update `astro.config.mjs`: `site: "https://<username>.github.io"`, `base: "/asag"` (hoặc đúng repo name)
- README ở `architecture/site/` ghi URL live

**Files**: `.github/workflows/deploy-architecture.yml`, `astro.config.mjs`, `architecture/site/README.md`.

**Verify**: push commit, Actions tab thấy workflow chạy xanh, URL https://<user>.github.io/asag mở được.

---

## Definition of Done (toàn project)

- [ ] `/` có hero + 4 feature card + thumbnail diagram + footer
- [ ] `/features` có 2 section (giáo viên / học sinh) với anchor links
- [ ] `/diagrams` index có 5 thẻ
- [ ] `/diagrams/high-level` SVG clickable mọi node
- [ ] 4 sub-pipeline diagram Mermaid clickable
- [ ] 13 component pages MDX, mỗi page đầy đủ 5 section + ProsConsTable
- [ ] Site mobile-friendly (test 360px width)
- [ ] Deploy GitHub Pages URL public truy cập được
- [ ] README ở `architecture/site/` link tới URL live + cách dev

---

## Gợi ý cho Claude Code khi thực thi

1. **Chạy `pnpm dev` ở background** và verify từng step bằng curl hoặc screenshot.
2. **Commit từng step** với message `arch-site: step X.Y - <output>`.
3. **Reference `sample-diagrams/*.png`** liên tục khi design SVG/Mermaid color & layout.
4. **Reference `../proposal.md`** và `../CLAUDE.md` cho nội dung kỹ thuật (đừng tự bịa).
5. **Nội dung MDX**: nếu không chắc — TODO comment + skip, hỏi Chris sau, đừng bịa.
6. **Không sửa code ở `../src/asag/`** — sub-project hoàn toàn tách biệt.
