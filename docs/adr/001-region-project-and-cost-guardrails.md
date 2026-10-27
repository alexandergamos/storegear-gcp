# ADR-001 — Region, project layout and cost guardrails

- **Status:** Accepted (2026-10-16)
- **Date:** 2026-10-16
- **Linear:** SMO-7
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Every Google Cloud resource lives in a **project** (the container for resources, permissions, billing and quotas). A project has **no region of its own**: each resource (database, Cloud Run service, Agent Platform call) picks its location when it is created. So the region has to be a team rule, applied every time.

What matters here:
- **Model availability:** new Gemini models and Agent Platform features don't reach every region at the same time.
- **Data residency:** staff chat history is personal data about employees, so GDPR applies. Product manuals are not personal data.
- **Latency:** Barcelona users; but model time (~2 s per call) dwarfs network distance within Europe.
- **Cost:** no free credits on this billing account (checked 2026-10-16), so every euro is real.

## Options considered

### Region
| Option | Pros | Cons |
|---|---|---|
| **europe-west1 (Belgium)** | Widest Agent Platform / Gemini coverage in the EU; every service we need; data stays in the EU | ~30–40 ms from Barcelona |
| europe-southwest1 (Madrid) | Lowest latency | Fewer AI services and later model availability |
| us-central1 (Iowa) | Models and features land first | Employee data outside the EU (GDPR transfer issues) |

### Project layout
| Option | Pros | Cons |
|---|---|---|
| **One project (`storegear-prod-ag26`)** | Simple; fits a 17-day build | Dev and prod share quotas, IAM and blast radius |
| One project per environment (dev / prod) | The standard: isolation, safe experiments | Double the setup and IAM work |

### Cost guardrails
| Option | Pros | Cons |
|---|---|---|
| Budget with alerts only | Production style: overspending beats an outage | Nothing stops a runaway loop |
| **Budget + enforced spend cap** | A hard stop: services pause at the cap | The agent goes down until the cap is lifted or the month resets |

## Decision
- **Region `europe-west1`** for every resource (Cloud SQL, Cloud Run / Agent Runtime, Agent Platform, Secret Manager replication, Artifact Registry).
- **One project:** `storegear-prod-ag26` (project number 1066603052728). Billing linked.
- **Budget €30 a month**, with alerts at 50 / 90 / 100 % actual and 100 % forecasted, plus an **enforced spend cap at €30**.
- **Console first, code-reproducible:** Alexander configures through the Cloud Console to learn. Every step is recorded with its `gcloud` equivalent in `infra/runbook.md`. **Terraform later** (Linear SMO-30).

## Consequences
- **Good:** the EU region covers the GDPR side and model availability. A hard cap rules out a surprise bill. The runbook keeps the project rebuildable.
- **Bad / accepted trade-offs:** there's no dev/prod isolation, so experiments run in the production project; mitigate with naming (`-dev` suffixes) and by deleting what isn't used. With the cap, a cost spike becomes an outage. Console clicks aren't reviewable in a PR the way code is.
- **Caveats:**
  - Some Gemini models may only be available through the **global** endpoint, which doesn't guarantee that processing stays in the EU. Check model availability in europe-west1 during SMO-9 and record any exception here.
  - Billing data lags by up to about 24 h, so a cap reacts late to a fast spike.
  - Enforced caps reset at the start of each month and resume paused services (Google's update, seen in the Console on 2026-10-16).
  - A new project enables ~50 APIs by default (BigQuery, Compute, Dataplex…). We use only those listed in the runbook.
  - The billing account also has a Google Maps Platform default budget (€50, 23 services) from another project. Leave it alone.

## Addendum (2026-10-16, SMO-9): model endpoint
Tested with real calls from the project:

| Endpoint | Gemini models served |
|---|---|
| `europe-west1` | Only the 2.5 family (2.5 Flash, 2.5 Flash-Lite, 2.5 Pro, TTS, Live) |
| `global` | All of them, including 3.x (3.5, 3.6, 3.7, **3.8 Flash**) and `gemini-embedding-2`. **No guarantee where ML processing happens** |
| `eu` (jurisdictional multi-region) | **`gemini-3.8-flash` works**; `gemini-2.5-flash` doesn't |

**Decision (Alexander):** model calls go through the **`eu`** endpoint with **`gemini-3.8-flash`**, the same model as the n8n baseline. That keeps the eval comparison fair: one change (the architecture), not two. All *resources* (Cloud SQL, runtime, secrets, registry) stay in **`europe-west1`**.

- **Why:** Google's data-residency docs say ML processing on jurisdictional endpoints stays within that jurisdiction (the EU). Regional endpoints not listed in the tables carry no processing guarantee.
- **Caveat to check:** the model-by-location table didn't render fully, so 3.8 Flash's EU guarantee is confirmed by a working call, not yet by the table. Check it in the console docs before any real users arrive. `eu` can process anywhere in the EU, not only in Belgium.
- **Alternative kept:** `gemini-2.5-flash` on `europe-west1` (strictest residency, older model).
- **Open for SMO-11:** the embedding model. `gemini-embedding-2` showed up on `global`; check `eu` / `europe-west1` before re-embedding.

## Addendum (2026-10-27): backup model on overload
- **What happened:** on 27 Oct the `eu` endpoint of `gemini-3.8-flash` answered 504 after ~12 s several times in a row. With min instances on, two questions still took 50 s and 59 s, and one of them failed. The retries went to the same endpoint and hit the same overload.
- **Decision (Alexander):** one attempt on `eu`. On a 5xx, 429 or timeout, the same call goes to the alternative kept above: **`gemini-2.5-flash` on `europe-west1`**, with a 512-token thinking budget (2.5 models take a budget, not a level). The backup gets two attempts. Processing stays in the EU. A 4xx other than 429 is raised, never hidden.
- **Rejected:** `gemini-3.8-flash` on `global`. It gives the same quality but no guarantee that processing stays in the EU.
- **Cost of the choice:** answers given during an overload come from an older model. The agent logs every switch with a `[model] ... falling back to` line, so the share of backup answers can be counted.
- **Timeout (same day, after the first live switch):** the primary waited 12 s for a 504 before the switch, and the question took 21.9 s. Answered 3.8 Flash calls that day took a median 2.0 s (p90 3.6 s, 2 of 36 over 6 s, both during the overload), so the primary got 6 s and the backup kept 15 s. **Measured right after:** the server answers 504 about 3 s before the client timeout (15 s gave a 504 at ~12 s, 6 s gave one at ~3 s), so 6 s cut at ~3 s, below the p90, and 4 of 10 test questions went to the backup. The primary now gets **10 s** (`STOREGEAR_PRIMARY_TIMEOUT_MS`), a cut at ~7 s. The switch is logged with the logger: the first version used `print`, which never reached Agent Runtime's logs.
- **Code:** `agent/storegear/fallback.py`. The models and locations can be overridden with the env vars `STOREGEAR_FALLBACK_MODEL` and `STOREGEAR_FALLBACK_LOCATION`.

## Revisit when
- A second person or a real customer uses the agent: split dev and prod projects and drop the hard cap in favour of alerts plus on-call.
- A required model is missing in europe-west1.
- Monthly cost passes about €20 while still idle: review Cloud SQL sizing.

## Learn more
- Locations for Vertex AI generative AI: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations
- Budgets and alerts: https://cloud.google.com/billing/docs/how-to/budgets
- Resource hierarchy: https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy
