# ADR-004 — Vector store: Cloud SQL for PostgreSQL + pgvector

- **Status:** Proposed
- **Date:** 2026-10-16
- **Linear:** SMO-10
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
The n8n agent's retrieval is **one SQL query** (n8n repo, `StoreGear - Hybrid Search (pgvector)`) that combines:
- **dense** ranking with pgvector (cosine distance, 1024-dim embeddings);
- **keyword** ranking with **Spanish full-text search** (`to_tsvector('spanish', …)`, so "batería"/"baterías" match), weighted by IDF, requiring at least 2 matching terms;
- a **role filter** (`access_level` staff/manager, from the verified token);
- **weighted parent-level Reciprocal Rank Fusion** (k = 60, dense 1.0, keyword 0.5), returning the top parent sections.

It scored 18/18 on the retrieval benchmark and is part of the 5.00 eval baseline. The data is small: about 9,062 child chunks plus their parents, roughly 40 MB of vectors.

The 2026-10-08 comparison in n8n already found that Pinecone hybrid, Qdrant and Weaviate lack Spanish stemming for keyword search. That's why n8n moved to Postgres.

## Options considered
| Option | What it is | Pros | Cons | Cost (rough, europe-west1) |
|---|---|---|---|---|
| **Cloud SQL for PostgreSQL + pgvector** | Managed Postgres; pgvector is a free extension | The n8n query ports **unchanged**; Spanish FTS; role filter in SQL; IAM DB auth (ADR-002); same engine as the baseline, so the comparison stays fair | We size and manage an instance; it's always on unless stopped | Shared-core db-f1-micro ≈ $13/month, db-g1-small ≈ $26/month, plus storage ~$2 |
| AlloyDB for PostgreSQL | Google's high-performance Postgres (ScaNN vector index, columnar engine) | Faster vector search at scale; AI features in the DB | Built for far bigger workloads; minimum instance size costs well over €100/month, which breaks the €30 cap | High |
| Vector Search 2.0 (Agent Platform) | Fully managed vector database with built-in text search and hybrid RRF | No database to run; scales to billions; optional auto-embeddings | Keyword-search language support (Spanish stemming) not documented in what we found; the IDF weighting, 2-term rule and parent-level RRF would need rework; release status of hybrid unclear | Not confirmed |
| RAG Engine (Agent Platform) | Managed end-to-end RAG: ingest, chunk, embed, retrieve | Least code | Gives up our chunking, injection check, role filter and RRF, so the eval comparison loses its meaning; the least learning | Not confirmed |

## Decision (proposed)
**Cloud SQL for PostgreSQL (Enterprise edition, latest supported major version) with pgvector**, in `europe-west1`:
- **Size:** shared-core **db-f1-micro** (0.6 GB RAM), single zone (no HA), 10 GB SSD, daily automated backups (7 kept). It's enough for ~10k chunks: the vectors fit in memory, and even a full scan is milliseconds at this size. Upgrade to db-g1-small only if p50 search latency is worse than n8n's 1.3 s.
- **Connectivity:** public IP **with no authorized networks**, so it's reachable **only through the Cloud SQL connectors** (TLS plus IAM checks). This avoids building a private network (VPC) for now.
- **Auth:** **IAM database authentication** on (`cloudsql.iam_authentication`). `sg-agent` and `sg-ingestion` are DB users with no passwords. The built-in `postgres` admin password is generated once, stored in Secret Manager, and used only for setup.
- **Cost control:** **stop the instance when not working** (activation policy "never"). A stopped instance costs only storage.

## Consequences
- **Good:**
  - The retrieval code is the proven one.
  - Spanish stemming is kept.
  - There are no DB passwords in the app.
  - It costs about €13 a month, or less if the instance is stopped at night.
- **Bad / accepted:**
  - Shared-core instances have **no SLA** and bursty CPU. Acceptable for a master's project, not for a real store.
  - Stopping the instance means the agent is down while it's stopped. Starting it takes a few minutes.
  - Public IP plus connectors is a pragmatic choice; a private IP is the stricter enterprise default.
- **Caveats:**
  - The embedding dimension must match the column (`vector(1024)`); the model is decided in SMO-11.
  - Use an **HNSW** index (or none at this size); test both.
  - IAM DB users need explicit `GRANT`s on tables.
  - Committed-use discounts don't apply to shared-core instances.

## Revisit when
- More than ~100k chunks, or p95 search over 1 s: move to db-g1-small or a dedicated core, then consider AlloyDB.
- Real users: add HA, private IP and point-in-time recovery.
- If Vector Search 2.0 documents Spanish text analysis, it becomes a serious "no database to run" alternative.

## Learn more
- Cloud SQL pricing: https://cloud.google.com/sql/pricing
- pgvector on Cloud SQL: https://cloud.google.com/sql/docs/postgres/work-with-vectors
- IAM database authentication: https://cloud.google.com/sql/docs/postgres/iam-authentication
- Cloud SQL Python Connector: https://github.com/GoogleCloudPlatform/cloud-sql-python-connector
- Vector Search 2.0 intro: https://codelabs.developers.google.com/vector-search-2-intro
