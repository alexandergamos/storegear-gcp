# ADR-008 — Runtime: Agent Runtime (eu) with the sg-agent service account

- **Status:** Proposed
- **Date:** 2026-10-18
- **Linear:** SMO-15
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
The agent passes the eval gate locally (ADR-007) and now needs to run in Google Cloud behind an endpoint. Requirements: EU processing (ADR-001), the existing least-privilege identity (ADR-002: Cloud SQL IAM user, Viewer on the price Sheet), managed sessions for conversation memory (SMO-24), low idle cost, and latency at least as good as n8n's 9 s.

## Options considered
| Option | Pros | Cons |
|---|---|---|
| **Agent Runtime** (Agent Platform; formerly Agent Engine / reasoning engines) | Built for ADK: `AdkApp` deploys in one call; **managed Sessions and Memory Bank**; traces to Cloud Trace; Agent Registry; available in `europe-west1` and the `eu` multi-region; **idle time between turns isn't billed** | Less portable; some scaling controls in Preview; default quota 90 queries/min per project and region |
| Cloud Run | Portable container; mature revisions and traffic splitting; custom routes and middleware | We'd build the HTTP layer and wire sessions ourselves; default in-memory sessions are lost when instances recycle |
| GKE | Maximum control | Cluster operations; overkill for one agent |

Compute prices are near-identical between Agent Runtime and Cloud Run, so the choice is about how much the platform manages for us.

## Decision (proposed)
- **Agent Runtime, location `eu`** (EU multi-region). Inside the runtime the SDK uses the deploy location for model calls. `europe-west1` doesn't serve Gemini 3.8 Flash or `gemini-embedding-2`, while `eu` serves both, plus Sessions and Memory Bank, under the same EU jurisdiction (ADR-001 addendum).
- **Identity: our `sg-agent` service account** (`service_account` in the deploy config), not the new Agent Identity. It already has the right Cloud SQL IAM user and Sheet share. The env var `STOREGEAR_DB_USER` names its DB user explicitly.
- **Packaging:** deploy from object (`AdkApp`) with our `storegear` package as `extra_packages`. Requirements are pinned to what we run locally. Staging bucket `gs://storegear-prod-ag26-agent-staging` (EU).
- **Sizing:** `min_instances=0` (no cost when idle; cold starts accepted and measured), `max_instances=2`, 1 vCPU / 2 GiB to start, raised only if latency needs it.
- **Config:** env vars only, no secrets (the agent needs none: Google APIs and the DB use IAM).

## Consequences
- **Good:** sessions and memory come managed (SMO-24 becomes configuration). One EU endpoint for runtime, model and embeddings. The least-privilege identity is unchanged.
- **Bad / accepted:** the runtime sits in `eu`, not strictly `europe-west1` (Cloud SQL stays in europe-west1; the connector link crosses EU regions over TLS). Cold starts after idle periods.
- **Caveats:**
  - Pickled deploys must import cleanly in the runtime. The DB and genai clients are created lazily on first use, never at import.
  - The 90 queries/min quota is fine for one shop.
  - The 15 s model timeout and retries from ADR-007 travel with the agent.

## Revisit when
- Cold starts hurt real users: set `min_instances=1` and price it.
- Agent Identity becomes the default for Agent Gateway policies (SMO-23): migrate the grants from `sg-agent`.

## Learn more
- Agent Runtime: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime
- Quickstart (ADK): https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk
- Supported locations: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-locations
- Runtime choice (Agent Runtime vs Cloud Run): https://wdenniss.com/agents/runtime-choice/
