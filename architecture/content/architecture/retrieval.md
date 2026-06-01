---
title: "Retrieval Pipeline"
---

# Retrieval Pipeline (Pipeline 2)

> Online, shared by Q&A, quiz generation, and slide generation. Returns the 5–8 most relevant chunks for any query in a given notebook.

## Why it exists

The quality of every downstream LLM answer is bounded by what the retriever feeds it. A great LLM with bad retrieval still hallucinates. Plain semantic search misses exact matches; plain keyword search misses synonyms. The pipeline below combines both, then refines with a cross-encoder.

## Steps

### 1. Embed the query
The user's question is embedded with **the same** BGE-M3 model used at ingest time. Cross-model comparison is meaningless, so this constraint is non-negotiable.

### 2a. Dense (semantic) search
SQL roughly:

```sql
SELECT id, content
FROM chunks
WHERE notebook_id = :nb               -- privacy: never cross notebooks
ORDER BY embedding <=> :query_vec     -- pgvector cosine distance
LIMIT 30;
```

The `<=> ` operator compares vectors. The HNSW index turns a brute-force comparison into an approximate-nearest-neighbour lookup, fast enough for millions of chunks.

Catches: "speed up queries?" matches a chunk about "index optimisation" even though the words are different.

### 2b. Sparse / BM25 search
Runs in parallel using either the BGE-M3 sparse weights or Postgres full-text search on a trigram / tsvector index. Also returns top 30.

Catches: exact tokens — error codes, version numbers, named entities — that dense search may smooth over.

### 3. Reciprocal Rank Fusion (RRF)
Two ranked lists arrive with scores on incompatible scales, so we fuse on rank rather than score:

```
score(chunk) = Σ  1 / (k + rank_in_list)         (k = 60 by convention)
```

A chunk that ranks high in both lists wins. Output: a single merged ranking, take top 20.

### 4. Reranker
The 20 candidates go through `bge-reranker-v2-m3` (a **cross-encoder**, not a bi-encoder):

- Bi-encoder (embedding) at step 2 encodes query and chunk separately. Fast but coarse.
- Cross-encoder takes the query and the chunk together and computes a fine-grained relevance score. Slower per pair, but applied only to 20 candidates.

The reranker reorders the 20 and keeps the top 5–8. Published benchmarks show this step adds ~17 percentage points to Recall@5 over hybrid alone — worth the latency cost.

### 5. Assemble context
Concatenate the surviving 5–8 chunks with their `source_id` / `chunk_id` / `page` so the consumer (Q&A, quiz, or slide) can cite them.

## Filtering and security

- The `WHERE notebook_id = :nb` clause inside both dense and sparse search is non-optional.
- Combined with Postgres Row-Level Security, a student cannot retrieve from a notebook they don't have access to.

## Components on the diagram

- `bge-m3` + `tei` (step 1)
- `pgvector` (step 2a)
- `pgvector` (step 2b — using GIN / FTS index)
- `bge-reranker` + `tei` (step 4)

## Practical tuning knobs

| Knob | Default | Trade-off |
|---|---|---|
| HNSW `m` / `ef_construction` | 16 / 64 | Higher → better recall, slower build |
| HNSW `ef_search` | 64 | Higher → better recall, slower query |
| Dense top-k | 30 | Larger → more recall, slower fusion |
| Sparse top-k | 30 | Same |
| Rerank top-n | 20 | Larger → more cost on cross-encoder |
| Final k | 5–8 | Smaller → cheaper LLM, less context |
