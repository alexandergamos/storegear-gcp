# ADR-012 — Drive sync: a scheduled reconciliation loop, plus a side-table rebuild

- **Status:** Proposed (2026-10-20)
- **Date:** 2026-10-20
- **Linear:** SMO-20
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Drive is the source of truth: the shop drops manuals into **"Shop Assitant"** (`1fcYTK5j8ZUl3w8kQDJjXoMA-0uZONsC6`, level `staff`) and its subfolder **"Internal (manager)"** (`17_mV7pI6GM7gifvGL1OxnTeWJMxaJO0j`, level `manager`). The catalog must follow it: new files appear, changed files are re-ingested, moved files change level, deleted files disappear. SMO-19 gave us the queue and the worker; this ADR is about **how we notice changes**. Phase 2 also closes with a full rebuild by the Google pipeline and the 22-question eval.

## Options: how to detect changes

| | **A. Polling + reconciliation (chosen)** | B. Drive push notifications (`changes.watch`) |
|---|---|---|
| How | Every N minutes: list both folders, compare with what the catalog holds, enqueue the differences | Drive calls our HTTPS endpoint when something changes |
| Latency | Up to N minutes | Seconds |
| Moving parts | The existing job + a Cloud Scheduler trigger | A public HTTPS endpoint, domain verification, channels that **expire (≤ 1 week) and must be renewed**, a page token to store |
| Missed events | Impossible by design: every run compares the full state | Notifications can be lost or arrive out of order, so you still need a periodic reconciliation as a safety net |
| n8n equivalent | n8n's Drive triggers also poll (every 5 min since backlog A10) | — |

**Reconciliation** is the reliability pattern behind A: don't trust events, compare *desired state* (Drive) with *actual state* (catalog) and fix the difference. It's how Kubernetes controllers and Terraform work. It's self-healing: if a run fails or a file was missed, the next run fixes it.

## Decision (proposed)
1. **`ingestion/sync.py`**, run by the same Cloud Run job before it drains the queue (`worker.py --sync`):
   - List PDFs in both folders (Drive API, `md5Checksum` included, no download).
   - Version key = `md5:access_level`, so a **move** between folders (same bytes, new level) is a new version.
   - **Add / change:** a file whose key differs from its last queued version → enqueue `upsert` (idempotent: an existing key is a no-op).
   - **Delete:** a file in the catalog that's no longer in Drive → enqueue `delete`. The pseudo-manual `polar-common` is never deleted.
   - **Guard:** if the listing returns **0 files**, no deletes at all (a Drive outage or a lost share must never wipe the catalog). It logs `SYNC_EMPTY_LISTING` at ERROR.
2. **Cloud Scheduler trigger** on the job, **every 15 minutes**. A new manual is searchable 15–20 min after upload; n8n does 5 min. The cost of an idle run is a few seconds of CPU.
3. **Full rebuild into side tables** (the Phase 2 gate, same safety pattern as SMO-17): an execution with `--sync --rebuild` and `STOREGEAR_CATALOG_SUFFIX=_v3` enqueues every Drive file for target `_v3`, processes them into empty `catalog_*_v3` tables, then runs **`fold_common`**: the corpus-level step that stores brand sections repeated in ≥ 3 Polar manuals once as "Polar · información común". Eval on `_v3`; swap only if it holds. Queue rows gain a `target` column, so a rebuild never collides with the live queue.

## Consequences
- **Good:** no new infrastructure besides a scheduler trigger; can't miss changes; self-healing; the catalog is provably rebuilt from Drive by the Google pipeline alone; the live catalog is untouched until the swap.
- **Bad / accepted:** up to ~15 min delay; each run lists Drive (2 API calls, far below quota); the rebuild costs ~$5 (parse + gate + embeddings for ~1,100 pages).

## Revisit when
Manuals must be searchable within seconds of upload, or the folder grows to thousands of files (then: `changes.list` with a stored page token instead of full listings).
