# Progress summary

*Updated 2026-10-17. Diagram: [`docs/diagram/progress.excalidraw`](diagram/progress.excalidraw), regenerated with `node docs/diagram/build_progress_diagram.js` after each Linear issue.*

## In one paragraph
We are rebuilding the StoreGear shop assistant, today a working n8n agent, entirely on Google Cloud, to learn how a real AI product is built and run. **Phase 0 (foundations) is done.** There's a Google Cloud project with an EU region and a hard spending cap. The code runs under robot identities with minimal permissions and no keys. A first ADK agent already talks to Gemini 3.8 Flash on Agent Platform. **Phase 1 has started:** the database that will hold the manuals is running (on a free 30-day trial), and next we create its tables and load the catalog.

## What we built, layer by layer

### 1. Ground rules (SMO-6)
- **What:** a repo (`storegear-gcp`) with folders for the agent, ingestion, eval and infra, plus a decision log.
- **Why it matters:** every important choice is written down as an **ADR** before the code: options, pros and cons, cost, and when to revisit. Five so far, ADR-000 to ADR-004.
- **n8n equivalent:** the backlog and build log, but now the decisions travel with the code.

### 2. The cloud "account" and its safety net (SMO-7 · ADR-001)
- **What:** project `storegear-prod-ag26`, with billing linked and a **€30/month budget with an enforced cap** that pauses services if crossed.
- **Region rule:** every resource lives in `europe-west1` (Belgium).
- **Why it matters:** a project is just a container, and the region is a team rule applied to each resource. The cap means a bug can't produce a surprise bill.

### 3. Who is allowed to do what (SMO-8 · ADR-002)
- **What:** two **service accounts**, robot identities for software. `sg-agent` (the agent, 6 permissions) and `sg-ingestion` (the PDF pipeline, 4 permissions).
- **No key files, ever.** Google hands out short-lived tokens automatically, and on the laptop your own login stands in (ADC).
- **Why it matters:** if the agent were tricked, by prompt injection for example, it still couldn't do more than its few permissions allow. In n8n, one credential manager held all the keys.

### 4. The first agent (SMO-9 · ADR-003)
- **What:** Python 3.12 + **ADK 2.12**, Google's agent framework. `hello_agent` has one tool and runs in `adk web`.
- **What we saw:** the full loop, event by event. Question → the model decides to call the tool → your Python function runs → the model writes the answer.
- **Key discovery:** **the region decides which models you get.** `europe-west1` only serves Gemini 2.5. Gemini 3.8 Flash (the n8n model) is available on the **`eu` endpoint**, which keeps processing inside the EU. Decision: `eu` + 3.8 Flash, so the comparison with n8n is fair.
- **Platform rename:** Vertex AI became **Gemini Enterprise Agent Platform** in April 2026. You caught that, and the plan now uses its built-in runtime, sessions, evaluation and observability.

### 5. The database (SMO-10 · ADR-004)
- **Why Postgres + pgvector:** the n8n search is one SQL query mixing meaning-based search (vectors) with **Spanish keyword search** (stemming). Postgres is the only option that runs it unchanged.
- **What:** you found a **free 30-day trial** instance, `sg-catalog` (PostgreSQL 18, a large machine, €0). It has a `storegear` database and passwordless **IAM database users** for both robots and for you. The admin password is in Secret Manager.
- ⚠️ **Never click "Upgrade"** on the trial. It ends around 16 November by stopping; it never starts charging. Reminder set for 10 November.

## What's next
| Next | Issue | What happens |
|---|---|---|
| 1 | SMO-10 | Create the tables, pgvector and Spanish search columns, and grant access to the robots |
| 2 | SMO-11 | Export the catalog from n8n, re-embed it with a Google embedding model, load it |
| 3 | SMO-12 | Port the hybrid search query as an agent tool; retrieval test must stay at 18/18 |
| 4 | SMO-13 / 14 / 15 | Real StoreGear agent → 22-question eval → deploy. That completes Phase 1 (due 21 Oct) |

## Numbers to beat (n8n, 2026-10-11)
Correctness 5.00 · Faithfulness 4.95 · Context 5.00 · Answer 5.00 · median 9.0 s · ~$0.008 per answer.
