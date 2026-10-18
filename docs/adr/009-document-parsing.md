# ADR-009 — Document parsing: Gemini 3.8 Flash, with a coverage check and Document AI as fallback

- **Status:** Proposed
- **Date:** 2026-10-18
- **Linear:** SMO-16
- **Deciders:** Alexander (decides) · Claude (drafts and tests)

## Context
Ingestion starts by turning each PDF manual into structured text (headings, paragraphs, tables). Retrieval quality depends on it: eval Q6 fails today because a spec-table row ("Impermeabilidad: 30 m") was flattened next to unrelated text. n8n used LlamaParse (third-party, outside ADR-000's Google-only scope), which also dropped the second line of a merged table cell in the Instinct 3 battery table (backlog A20).

## Test (2026-10-18, `ingestion/parser_test.py`)
Three excerpts with known traps: Ignite 2 specs (pp. 103–105), Instinct 3 battery table (pp. 99–100), Suunto Ocean battery modes (pp. 28–30).

| | Gemini 3.8 Flash (PDF in, Markdown out, `eu`) | Document AI Layout Parser (`eu`, processor `8a9ba69484bf2664`) |
|---|---|---|
| Traps kept | **9/9** | **9/9** |
| Ignite 2 "30 m" row | `\| Impermeabilidad: \| 30 m / (ISO 22810, apto para natación) \|` | `\| Impermeabilidad: \| 30 m (ISO 22810, apto para natación) \|` |
| Instinct merged cell ("7 días… siempre enc") | Kept, right columns | Kept, right columns |
| Multi-line cells in other rows | **One row**, lines joined with " / " | Often **split into extra rows with an empty label cell**, so the value loses its label (the Q6 failure pattern) |
| Text cleanliness | Clean | OCR glitches (`delnstinct`, `-10^{\circ}C~a+50^{\circ}C`, stray page numbers and symbols) |
| Word coverage vs raw PDF text | 97–100 % | 99–100 % |
| Time per 2–3 page excerpt | 11–36 s | 5–7 s |
| Determinism | No (LLM) | Yes |
| Price (measured tokens: 587 in + 564 out per page, no thinking at low) | **≈ $2.6 per 1,000 pages** (≈ $2.8 for the ~1,100-page catalog) at the introductory $0.75 / $3.75 per M tokens; ≈ $5.1 from 2027 (price doubles); ≈ $1.3 in batch mode | $10 per 1,000 pages (≈ $11 for the catalog) |

Price check: at the same rates one agent answer (~9,900 in / ~138 out tokens) costs ≈ $0.0079, matching n8n's Langfuse-measured $0.008 with the same model. Gemini prices come from third-party listings (Google's pricing page didn't load); confirm in billing (SMO-26).

## Options considered
| Option | Pros | Cons |
|---|---|---|
| **Gemini 3.8 Flash as parser** | Best table structure for retrieval; clean text; ~4× cheaper than Document AI today (~2× from 2027); same model and endpoint we already use; instructions can be tuned (e.g. "repeat the column header") | An LLM can skip or rephrase; slower; needs page batching |
| Document AI Layout Parser | Deterministic, fast, purpose-built, cheap per page | Splits multi-line table cells into label-less rows; OCR artefacts to clean up |
| Both, combined | Each page parsed by Gemini, verified against Document AI or raw text | More moving parts |
| LlamaParse (n8n) | Known | Third party, outside ADR-000; dropped table lines (A20) |

## Decision (proposed)
**Gemini 3.8 Flash as the primary parser, in batches of a few pages, with an automatic coverage check:**
1. Each batch of pages is parsed by Gemini with the tested prompt (copy verbatim, tables as Markdown, multi-line cells joined with " / ").
2. **Coverage check:** compare the Gemini text's words with the page's raw text (pypdf). Below a threshold (start at 95 %) the batch is re-parsed with **Document AI Layout Parser**, and the fallback is logged.
3. The processor `sg-layout-parser` (`eu`) stays as the fallback. `sg-ingestion` gets *Document AI API User* when ingestion moves to the cloud (SMO-19).

## Consequences
- **Good:** table rows keep their labels (the root cause of Q6); clean text for embeddings and keyword search; the LLM's risk of skipping text is measured on every batch rather than trusted.
- **Bad / accepted:** slower ingestion (pages in parallel; it runs offline, not in the answer path); two parsers to maintain. Cost is not a downside: ~$3 per full re-ingest against ~$11 with Document AI alone.
- **Caveats:** the raw-text reference is unreliable on some PDFs (Ignite excerpt: 56 % for both parsers because pypdf glues words), so the threshold is compared per manual, not globally. Prompt changes to the parser are re-tested on the three trap excerpts.

## Revisit when
- Full-manual runs show Gemini coverage regularly below the threshold, or its cost is above a few euros per full re-ingest.
- A Document AI version handles multi-line cells as one row.

## Learn more
- Document AI Layout Parser: https://cloud.google.com/document-ai/docs/layout-parse-chunk
- Document AI pricing: https://cloud.google.com/document-ai/pricing
- Document AI regions: https://cloud.google.com/document-ai/docs/regions
- Gemini document understanding: https://docs.cloud.google.com/gemini-enterprise-agent-platform
