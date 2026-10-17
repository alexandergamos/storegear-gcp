# ADR-005 — Embedding model: gemini-embedding-2 (1024 dims, eu endpoint)

- **Status:** Accepted (2026-10-17)
- **Date:** 2026-10-17
- **Linear:** SMO-11
- **Deciders:** Alexander (decides) · Claude (drafts and benchmarks)

## Context
Embeddings turn each passage (and each question) into a vector, so that "meaning-close" texts end up close together. That's the dense half of the hybrid search. n8n used OpenAI `text-embedding-3-small` at 1024 dimensions. ADR-000 requires Google only, so the catalog (9,054 chunks from 10 manuals, exported from n8n's Supabase) must be re-embedded with a Google model. The table column is `vector(1024)` (ADR-004).

## Options considered (tested from the project, 2026-10-17)
| Model | Endpoint that serves it | 1024 dims | Batching | Notes |
|---|---|---|---|---|
| `gemini-embedding-001` | `europe-west1` ✅ (`eu` ❌) | ✅ | ✅ 25 per call | Strict regional residency |
| **`gemini-embedding-2`** | `eu` ✅ (`europe-west1` ❌) | ✅ | ⚠️ **one text per call** | Newer; same endpoint as our Gemini 3.8 Flash |
| `text-multilingual-embedding-002` / `text-embedding-005` | — | ❌ (max 768) | — | Would need a schema change |

## Benchmark (vector search only, 17 eval questions with a known source manual)
| Model | Right manual 1st | Right manual in top 5 | MRR |
|---|---|---|---|
| gemini-embedding-001 | 13/17 | 17/17 | 0.848 |
| **gemini-embedding-2** | **16/17** | **17/17** | **0.953** |

`gemini-embedding-001` confuses sibling Polar manuals (Vantage M2 vs V2, Grit X Pro vs X2). Script: `eval/retrieval_benchmark.py`; embeddings cached in `data/` (git-ignored).

## Decision
**`gemini-embedding-2`, 1024 dimensions, through the `eu` endpoint.** Documents are embedded with `task_type=RETRIEVAL_DOCUMENT`, queries with `RETRIEVAL_QUERY`. All 9,054 chunks were loaded into `catalog_chunks.embedding` with `ingestion/load_catalog.py`, connecting as `sg-ingestion`.

## Consequences
- **Good:** clearly better retrieval on our own data. The same endpoint and jurisdiction as the chat model (ADR-001 addendum), so there's one EU processing story. Cost is cents (about 9k short texts).
- **Bad / accepted:** not served in `europe-west1`, so the strict-regional option is lost. One call per text means slower bulk embedding (about 4–5 min for the catalog with 12 parallel workers), which is fine for ingestion.
- **Caveats:**
  - ⚠️ **`gemini-embedding-2` treats a list of texts as ONE input and returns ONE vector.** Batching silently corrupts the index. `embed_export.py` checks that the number of vectors equals the number of texts and fails loudly otherwise.
  - The vectors are normalised, so cosine distance is the right measure (`vector_cosine_ops` index).
  - Changing the model later means re-embedding everything; vectors from different models are not comparable.

## Revisit when
- The full hybrid benchmark (SMO-12) or the 22-question eval (SMO-14) shows retrieval misses that trace back to embeddings.
- A Google embedding model becomes available in `europe-west1` with equal quality and strict residency matters.

## Learn more
- Gemini embeddings on Agent Platform: https://docs.cloud.google.com/gemini-enterprise-agent-platform
- Task types for embeddings: https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/task-types
