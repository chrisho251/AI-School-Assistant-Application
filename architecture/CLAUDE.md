# CLAUDE.md — Sub-project: ASAG Architecture Site

> File này dành riêng cho Claude / Claude Code khi làm việc trên thư mục `E:\study\ASAG\architecture\`.
> Sub-project này **độc lập** với codebase ASAG core ở `src/asag/`. Đừng trộn lẫn.

---

## 1. Sub-project tóm lược

Một **static documentation site** (landing + clickable architecture diagrams) showcase dự án ASAG (AI School Assistant & Grader).

- **Audience**: 3 nhóm
  1. **Người không tech** — phải hiểu ASAG làm gì sau 2 phút đọc trang chủ.
  2. **Reviewer portfolio / hội đồng Master** — thấy ngay kiến trúc + lý do chọn từng công nghệ.
  3. **Chris 6 tháng sau** — mở site là nhớ ngay tại sao Groq thay vì OpenAI.
- **Goal**: trực quan + interactive. Click vào component trên diagram → trang chi tiết về component đó.
- **Out of scope**: không phải app thực, không kết nối backend ASAG, không có dữ liệu động.

Project mẹ ở `E:\study\ASAG\` (xem `../CLAUDE.md`, `../proposal.md`, `../plan.md`).

---

## 2. Quyết định đã chốt — KHÔNG đổi nếu chưa hỏi

| Quyết định | Lý do |
|---|---|
| **Astro 5** làm framework | Static site, content-first, MDX, file-based routing, deploy free |
| **TailwindCSS** styling | Nhanh, mockup-friendly, không cần CSS-in-JS |
| **Mermaid** cho flow diagrams + **inline SVG hand-craft** cho high-level hero diagram | Mermaid `click` syntax cho clickable. SVG thuần với `<a>` cho pixel-perfect match phong cách sample-diagrams |
| **MDX** cho content (1 file / 1 component) | Markdown + Astro component reuse |
| **GitHub Pages** deploy | Free, tích hợp repo |
| **Node 20+**, **pnpm** package manager | Astro yêu cầu Node 18+, pnpm nhanh + disk-friendly |
| Site ngôn ngữ chính: **tiếng Việt** | Audience nội địa + reviewer Master |
| Không dùng React/Next/Vue | Astro đã đủ + tránh JS bloat |
| Không tracking / analytics ở phase đầu | Tránh phụ thuộc 3rd-party + GDPR |

---

## 3. Folder layout

```
architecture/
├── CLAUDE.md                  ← bạn đang đọc
├── plan.md                    ← lộ trình build site (cho Claude Code)
├── sample-diagrams/           ← 6 PNG mẫu phong cách diagram, KHÔNG xóa, dùng làm reference
└── site/                      ← Astro project (sẽ tạo theo plan)
    ├── astro.config.mjs
    ├── tailwind.config.mjs
    ├── package.json
    ├── tsconfig.json
    ├── src/
    │   ├── layouts/
    │   │   ├── BaseLayout.astro          ← header/footer/meta chung
    │   │   └── ComponentLayout.astro     ← layout chuẩn cho mỗi trang component
    │   ├── pages/
    │   │   ├── index.astro               ← landing (hero + features + high-level diagram)
    │   │   ├── features.astro            ← danh sách tính năng đầy đủ
    │   │   ├── diagrams/
    │   │   │   ├── index.astro           ← index tất cả diagram
    │   │   │   ├── high-level.astro      ← high-level architecture (SVG hand-craft)
    │   │   │   ├── ingestion.astro       ← Pipeline 1: ingestion
    │   │   │   ├── retrieval.astro       ← Pipeline 2: hybrid retrieval + rerank
    │   │   │   ├── assessment.astro      ← Quiz gen + auto-grading
    │   │   │   └── slide-generation.astro
    │   │   └── components/               ← 1 file MDX / 1 component
    │   │       ├── supabase.mdx
    │   │       ├── pgvector.mdx
    │   │       ├── docling.mdx
    │   │       ├── bge-m3.mdx
    │   │       ├── tei.mdx
    │   │       ├── bge-reranker.mdx
    │   │       ├── gemini-flash.mdx
    │   │       ├── groq-llama.mdx
    │   │       ├── litellm.mdx
    │   │       ├── langfuse.mdx
    │   │       ├── marp.mdx
    │   │       ├── fastapi.mdx
    │   │       └── streamlit.mdx
    │   ├── components/                   ← Astro components tái sử dụng
    │   │   ├── Hero.astro
    │   │   ├── FeatureCard.astro
    │   │   ├── DiagramFrame.astro        ← khung trắng bo góc + nền gradient (style sample)
    │   │   ├── ComponentNode.astro       ← box pastel có thể click
    │   │   ├── Mermaid.astro             ← wrapper render Mermaid + cho phép click
    │   │   ├── ProsConsTable.astro       ← bảng "free tier vs production alternative"
    │   │   └── Nav.astro
    │   ├── content/
    │   │   ├── config.ts                 ← content collection schema
    │   │   └── components/               ← optional: structured data cho component pages
    │   └── styles/
    │       └── global.css                ← @tailwind + custom (gradient bg giống sample)
    └── public/
        ├── favicon.svg
        └── diagrams/                     ← static SVG exports nếu cần
```

---

## 4. Visual style guide (bắt buộc match)

Tham khảo `sample-diagrams/*.png` — phong cách "Vectorize / IBM-ish":

- **Background**: gradient chéo tím-xanh (`from-indigo-500 via-violet-500 to-blue-500` hoặc tương tự)
- **Card frame**: nền trắng, bo `rounded-3xl`, shadow nhẹ, padding rộng (`p-8` trở lên)
- **Node boxes**: pastel mềm — `bg-amber-50` (vàng), `bg-sky-50` (xanh), `bg-emerald-50` (teal), `bg-rose-50` (hồng); border `border-slate-300`; bo `rounded-lg`
- **Arrows**: stroke màu xám đậm `stroke-slate-600`, đầu mũi tên rõ
- **Database**: hình trụ (SVG cylinder) màu nhạt
- **Stage bar dưới cùng** (như sample 1): các step nối liền bằng pill xám với mũi tên ">"
- **Typography**: sans-serif (font Inter của Tailwind), size vừa, không viết hoa toàn bộ
- **Click affordance**: node clickable có `hover:ring-2 hover:ring-indigo-400 transition` + cursor pointer
- **Mobile**: diagram scroll ngang nếu chật (`overflow-x-auto`), KHÔNG ép wrap (sẽ vỡ flow)

---

## 5. Content writing conventions

Đây là phần **quan trọng nhất**, vì audience #1 là người không tech.

### Quy tắc viết

1. **Mở đầu bằng metaphor** trước khi định nghĩa kỹ thuật. Ví dụ: *"Embedding giống như tọa độ GPS cho ý nghĩa của câu chữ — câu nào ý gần nhau thì tọa độ gần nhau."*
2. **Không assume kiến thức**. Lần đầu xuất hiện thuật ngữ → giải thích ngắn ngay trong ngoặc.
3. **Mỗi component page có cấu trúc cố định** (xem template ở section 6).
4. **Tiếng Việt** là mặc định. Technical term giữ nguyên tiếng Anh.
5. **Không slide marketing** — không "10x faster", "revolutionary". Trung thực: "rẻ hơn cho học tập, không phải tốt nhất tuyệt đối".
6. **Code snippet ngắn** (≤10 dòng) cho ai tò mò, đừng paste 50 dòng.

### Bad vs Good

❌ Bad: "BGE-M3 is a SOTA dense retrieval model with MTEB score 64.5."
✅ Good: "BGE-M3 là một model AI biến chữ thành dãy số, để máy tính có thể so sánh ý nghĩa giữa các đoạn văn. Nó hiểu được 100+ ngôn ngữ kể cả tiếng Việt — đây là lý do mình chọn nó thay vì model của OpenAI (chỉ tốt với tiếng Anh)."

---

## 6. Template trang component (MDX)

Mỗi file `src/pages/components/<name>.mdx` PHẢI theo cấu trúc này:

```mdx
---
layout: ../../layouts/ComponentLayout.astro
title: "<Tên hiển thị>"
category: "<storage | embedding | llm | infra | parsing | reranker | observability | ui | api>"
icon: "<emoji hoặc tên icon>"
usedInPipeline: ["ingestion" | "retrieval" | "qa" | "assessment" | "slides"]
---

## Trong ASAG, component này làm gì?

(1–2 đoạn dễ hiểu cho người không tech — bắt đầu bằng metaphor)

## Vai trò cụ thể trong pipeline

(Liệt kê pipeline + stage cụ thể, ví dụ: "Pipeline 1 — Stage 3: Embed" + 1 đoạn mô tả)

## Cách thức hoạt động (high-level)

(3–5 bullet hoặc 1 sơ đồ Mermaid nhỏ)

## Tại sao chọn nó cho version học tập

(Free tier? Self-host được? Học được gì? Hợp với stack?)

## Production alternative

import ProsConsTable from "../../components/ProsConsTable.astro";

<ProsConsTable
  current={{
    name: "<tên hiện tại>",
    tier: "free",
    pros: ["...", "..."],
    cons: ["...", "..."]
  }}
  alternative={{
    name: "<tên alternative>",
    tier: "paid / managed",
    pros: ["...", "..."],
    why_better: "..."
  }}
/>

## Đọc thêm

- [Docs official](https://...)
- [So sánh với X](https://...)
```

---

## 7. Mermaid clickable syntax (nhớ kỹ)

Mermaid hỗ trợ link node tới URL ngay trong text definition:

```
flowchart LR
  PDF[PDF / DOCX] --> Docling[Docling Parser]
  Docling --> Chunks[Chunks 1000 token]
  Chunks --> Embed[BGE-M3 Embedding]
  Embed --> DB[(pgvector)]

  click Docling href "/components/docling" "Mở trang Docling"
  click Embed href "/components/bge-m3" "Mở trang BGE-M3"
  click DB href "/components/pgvector" "Mở trang pgvector"
```

Wrapper `<Mermaid />` component phải:
- Render Mermaid client-side (`mermaid.initialize` + `mermaid.run`)
- Inject `securityLevel: "loose"` để click hoạt động
- Wrap trong `<DiagramFrame>` để có nền gradient + card

---

## 8. Common commands

```bash
cd architecture/site

# Install
pnpm install

# Dev (localhost:4321)
pnpm dev

# Build static
pnpm build              # output: dist/

# Preview build
pnpm preview

# Lint
pnpm astro check

# Deploy: push lên branch gh-pages (GitHub Actions tự build)
git push origin main    # workflow ở .github/workflows/deploy-architecture.yml
```

---

## 9. Anti-patterns — TRÁNH

- ❌ Hardcode tên service lung tung — mọi reference component phải đi qua MDX page tương ứng (1 nguồn duy nhất)
- ❌ Diagram chỉ là ảnh PNG — phải dùng SVG hoặc Mermaid để clickable + version control
- ❌ Viết content kiểu "rủi ro: nó là technology" — phải giải thích bằng ngôn ngữ đời thường
- ❌ Tạo trang component không có section "Production alternative" — đó là điểm nhấn portfolio
- ❌ Đụng vào code ASAG core ở `../src/asag/` — sub-project này KHÔNG sửa code chính
- ❌ Add tracking script (GA, Hotjar) — phase đầu giữ sạch
- ❌ Build site bằng React/Next/Vue khi Astro đủ
- ❌ Để emoji nhiều quá ở content (1-2 đầu trang là đủ)
- ❌ Để diagram tiếng Anh trong khi content tiếng Việt (nhất quán ngôn ngữ)

---

## 10. Khi Chris hỏi "làm gì hôm nay cho architecture site?"

Trả lời theo template:
1. Step hiện tại theo `architecture/plan.md` là Step <X>
2. Mục tiêu step: <copy từ plan>
3. File cần tạo/sửa: <list>
4. Output cuối step: <copy từ plan>
5. Đề xuất bắt đầu từ <command/action cụ thể>

---

## 11. Tham khảo

- Astro docs: https://docs.astro.build
- Astro + Tailwind: https://docs.astro.build/en/guides/integrations-guide/tailwind/
- Mermaid clickable syntax: https://mermaid.js.org/syntax/flowchart.html#interaction
- MDX in Astro: https://docs.astro.build/en/guides/markdown-content/
- TailwindCSS gradients: https://tailwindcss.com/docs/gradient-color-stops
- GitHub Pages + Astro: https://docs.astro.build/en/guides/deploy/github/
- Sample-diagrams folder: `./sample-diagrams/` — REFERENCE STYLE

---

**Last updated**: 2026-05-28
