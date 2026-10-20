# ADR-011 — Ingestion orchestration: a Postgres queue table drained by a Cloud Run job

- **Status:** Accepted (2026-10-20)
- **Date:** 2026-10-20
- **Linear:** SMO-19 (planned as "ADR-010"; renumbered because ADR-010 went to the injection check)
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Today ingestion is five scripts run by hand on a laptop (parse → chunk → injection gate → embed → load). Phase 2 needs it to run in the cloud, unattended, **one manual at a time and safe to retry**:
- **Idempotent:** the same file arriving twice (a duplicate event, a re-run, a retry) must not create duplicates or double cost.
- **Retries with a limit:** a failure is retried; after 3 attempts the job is **dead** and someone is alerted.
- **No stuck work:** a job whose worker crashed mid-way must be picked up again (stale-claim reaping).
- SMO-20 adds the producer: a scheduled Drive sync that enqueues adds, changes and deletes.

Volume is tiny: 10 manuals today, a few new or changed ones a month. Each manual takes minutes (parse ~2 min, gate ~1–2 min, embed ~1 min), so the unit of work is long, not frequent. The n8n build solved the same problem with a queue table + a worker workflow + a dead-letter email.

## Options

| | **A. Queue table in Cloud SQL + Cloud Run job** | B. Cloud Tasks → Cloud Run service | C. Pub/Sub (push) → Cloud Run service | D. Workflows |
|---|---|---|---|---|
| How it works | Producer inserts rows; a job starts (on schedule or on demand), claims rows with `FOR UPDATE SKIP LOCKED`, processes, exits | One task per manual; Cloud Tasks calls an HTTP endpoint and retries with backoff | One message per manual; Pub/Sub pushes to an endpoint, redelivers on failure, dead-letter topic after N tries | A YAML state machine calls each step, with retries per step |
| Retries / dead letter | Our code: `attempts`, `status = dead` | Built in (retries); no dead-letter: after max attempts the task is dropped | Built in, **including a dead-letter topic** | Built in per step |
| Dedupe | `UNIQUE (file_id, content_hash, action)`: a duplicate insert is a no-op | Task name dedupe (but only ~1 h window after deletion) | None: at-least-once, app must dedupe | Up to us |
| Long work (minutes) | Jobs run up to 24 h per task | Request timeout up to 30 min (HTTP target) | Push deadline ≤ 10 min ack, needs care | Fine (it waits on calls) |
| Visibility | **A SQL query** shows the queue, attempts, errors | Console list of tasks | Console metrics; messages not browsable once delivered | Console execution graph |
| New moving parts | Cloud Run job only (DB already exists) | Queue + service + IAM for the invoker | Topic + subscription + DLQ topic + service | Workflow + service(s) |
| Cost at our volume | ≈ $0 | ≈ $0 | ≈ $0 | ≈ $0 |

## Decision (proposed)
**Option A.** A table `ingest_queue` in the existing Cloud SQL database, drained by a **Cloud Run job** `sg-ingest-worker` running as `sg-ingestion`.

- **Idempotency:** `UNIQUE (file_id, content_hash, action)`, where `content_hash` is Drive's `md5Checksum` (the md5 of the bytes), so the Drive sync can dedupe without downloading. Enqueuing the same version of a file twice is a no-op; a changed file (new hash) is a new job. Loading a manual **replaces** all its chunks in one transaction, so re-processing the same file gives the same catalog.
- **Claiming:** `UPDATE … WHERE id = (SELECT id … WHERE status = 'queued' AND next_attempt_at <= now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING …`. Two workers can never take the same job, and no lock outlives a crashed worker.
- **Retries:** on failure `attempts + 1`, `next_attempt_at = now() + 2^attempts min`; at 3 attempts → `status = 'dead'` and a structured log line `INGEST_DEAD` that a **log-based alert** emails Alexander (this is the SMO-27 dead-letter + alert for ingestion).
- **Stale claims:** at start-up the job requeues rows `running` for more than 30 min (the worker died without finishing).
- **Pipeline per job:** download PDF (Drive API) → parse (Gemini + coverage + Document AI fallback) → chunk → **injection gate** (ADR-010; quarantined sections skipped) → embed → replace the manual's rows → `done`.
- **Triggers:** Cloud Scheduler runs the job (SMO-20 adds the Drive sync that enqueues before it). Manual runs from the Console for re-ingests.

**Why not the managed queues:** at 10 manuals a month, Cloud Tasks and Pub/Sub add a service, an endpoint, invoker IAM and (for Pub/Sub) a dedupe layer, and we'd still need a table to know the state of each manual. The table *is* the state machine; the job just drains it. They win at high volume, fan-out to many consumers, or when work must start within seconds of an event.

## Caveats
- **Per-manual chunking vs cross-manual folding:** `chunk_manuals.py` folds brand sections into "Polar · información común" by comparing *all* manuals. Per job, a new manual's brand sections are checked against the existing common copy (same title + similar text → skip); they don't create a new one. A full rebuild (SMO-20) still runs the corpus-level fold.
- **Cloud SQL trial ends ~16 Nov:** the queue lives with the catalog, so it follows whatever ADR-004's post-trial decision is.
- **The job holds no secrets:** identity is `sg-ingestion` (Vertex AI, Document AI, Drive read, Cloud SQL IAM login). New roles: `roles/aiplatform.user`, `roles/documentai.apiUser`, `roles/run.invoker` for the scheduler, `roles/logging.logWriter`.

## Consequences
- **Good:** one new runtime piece; queue state visible with SQL; same design as n8n, so the final comparison (SMO-29) is like for like; retries, dead letter and alert covered.
- **Bad / accepted:** retry/backoff logic is ours to test; the job polls (a scheduled run) instead of reacting instantly, fine for manuals that change monthly.

## Addendum (2026-10-20): built and tested locally
- `infra/sql/005_ingest_queue.sql`, `ingestion/pipeline.py` (one manual end to end, replace in one transaction), `ingestion/worker.py` (reap → claim → run → done / retry / dead), `ingestion/enqueue.py` (manual enqueue), `Dockerfile` + `.gcloudignore` whitelist (only code and the lock file are uploaded; manuals never leave the laptop).
- **Tests on the live database:** enqueue twice → second is a no-op; the internal manual re-ingested end to end (6 sections, 10 chunks, manager level, 106 s); a missing file → `queued` with retry in 2 min, then 4 min; a job on its last attempt → `dead` + `INGEST_DEAD` at ERROR; a job stuck `running` for an hour → reaped and retried.
- **Cloud Run job `max-retries = 0`:** retries belong to the queue, not to Cloud Run. If Cloud Run also retried, a failed manual would be retried on two levels at once.

## Revisit when
Volume reaches many files a day, ingestion must start within seconds of an upload, or more than one consumer needs the same events → Pub/Sub with a dead-letter topic.
