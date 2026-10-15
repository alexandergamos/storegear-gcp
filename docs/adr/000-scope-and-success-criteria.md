# ADR-000 — Rebuild StoreGear 100% on Google Cloud: scope and success criteria

- **Status:** Proposed
- **Date:** 2026-10-15
- **Linear:** SMO-6
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
StoreGear Assistant is a RAG agent for shop staff. It answers questions from smartwatch manuals (Garmin, Polar, Suunto) and checks live price and stock. It runs in production on n8n Cloud, with eval scores of 5.00 / 4.95 / 5.00 / 5.00, a median latency of 9.0 s and a cost of about $0.008 per answer. That build is the master's deliverable, and the thesis write-up is done.

The challenge: rebuild the same product using **only Google Cloud** services, by 31 Oct 2026. Capacity is 3–4 h per weekday, more on weekends (about 60–70 h in total). The point is to learn how a real AI product is designed, deployed and operated with code and managed cloud services, instead of a visual workflow tool.

## Options considered
| Option | Pros | Cons | Effort |
|---|---|---|---|
| A. Keep n8n only | Zero risk | No learning; no code-first production experience | 0 |
| B. Port only the agent to ADK; reuse the n8n MCP server as tools | Fast; a clean "two runtimes, same tools" comparison | Not 100% Google Cloud; skips ingestion, security and ops, where most production lessons are | ~2–3 days |
| C. **Full rebuild on Google Cloud, in phases** | Covers the whole production stack; every phase leaves a working system | Tight timeline; new services to learn; cloud cost | ~60–70 h |

## Decision
**Option C**, delivered in five phases, each ending with the 22-question eval:
0. Foundations: project, budget, IAM, secrets, toolchain.
1. Working agent: Cloud SQL + pgvector, embeddings, hybrid search, ADK agent, eval harness, deployment.
2. Ingestion.
3. Safety: threat model, auth, PII, guardrails, memory.
4. Ops: tracing, cost, alerts, dead-letter queue, CI/CD.

**In scope:** feature parity with the n8n agent for answering, ingestion, role-based access, safety and operations.

**Out of scope (backlog):** Terraform, MCP/A2A exposure, streaming, a front-end app.

## Success criteria
| Criterion | Target |
|---|---|
| Quality | 22-question eval ≥ n8n baseline minus 0.1 on each metric |
| Retrieval | Benchmark 18/18 |
| Latency | Median ≤ 9 s on the same 10 questions (stretch: faster) |
| Cost | ≤ $0.01 per answer at runtime; idle infrastructure cost known and within budget |
| Security | Secrets in Secret Manager, no key files, least-privilege service accounts, role from the token, PII masked |
| Operability | Traced requests, alerts, dead-letter queue, eval-gated deploys |
| Learning | One ADR per major choice; one build-log entry per issue; Alexander can explain every component |

**Minimum acceptable result:** Phase 1 green (deployed agent passing the eval). Each later phase adds to it.

## Consequences
- **Good:** hands-on experience across the full AI production lifecycle, and a direct n8n vs code-first comparison for the thesis annex.
- **Bad / accepted trade-offs:** scripted gcloud instead of Terraform; a single project rather than separate dev and prod; some n8n features may be simplified to fit the time.
- **Caveats:** Cloud SQL is always on, so it costs money even when idle. Vertex AI quotas and model availability depend on the region. Re-embedding means retrieval may differ from n8n until it's tuned.

## Revisit when
Phase 1 slips past 21 Oct. In that case, drop Phase 4 to its essentials (alerts + dead-letter queue) and protect the comparison on 31 Oct.

## Learn more
- ADK docs: https://google.github.io/adk-docs/
- Vertex AI generative AI docs: https://cloud.google.com/vertex-ai/generative-ai/docs
- ADRs: https://adr.github.io/
