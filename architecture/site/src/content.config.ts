import { defineCollection } from "astro:content";
import { z } from "astro:schema";
import { glob } from "astro/loaders";

const components = defineCollection({
  loader: glob({ pattern: "*.md", base: "../content/components" }),
  schema: z.object({
    title: z.string(),
    category: z.enum([
      "storage", "embedding", "llm", "infra",
      "parsing", "reranker", "observability", "ui", "api", "security",
    ]),
    icon: z.string().optional(),
    usedInPipeline: z
      .array(z.enum(["ingestion", "retrieval", "qa", "assessment", "slides"]))
      .default([]),
    current: z.object({
      name: z.string(),
      tier: z.string(),
      pros: z.array(z.string()),
      cons: z.array(z.string()).optional(),
    }).optional(),
    prodAlternative: z.object({
      name: z.string(),
      tier: z.string(),
      pros: z.array(z.string()),
      why_better: z.string(),
    }).optional(),
    status: z.enum(["in-use", "planned"]).optional(),
    summary: z.string().optional(),
  }),
});

const architecture = defineCollection({
  loader: glob({ pattern: "*.md", base: "../content/architecture" }),
  schema: z.object({ title: z.string() }),
});

const features = defineCollection({
  loader: glob({ pattern: "*.md", base: "../content/features" }),
  schema: z.object({
    title: z.string(),
    audience: z.enum(["teacher", "student"]),
  }),
});

export const collections = { components, architecture, features };
