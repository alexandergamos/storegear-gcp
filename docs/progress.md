# Progress summary

*Updated 2026-10-17 (after SMO-14). Diagram: [`docs/diagram/progress.excalidraw`](diagram/progress.excalidraw), regenerated with `node docs/diagram/build_progress_diagram.js` after each Linear issue.*

## In one paragraph
We are rebuilding the StoreGear shop assistant, today a working n8n agent, entirely on Google Cloud, to learn how a real AI product is built and run. **Phase 0 (foundations) is done.** There's a Google Cloud project with an EU region and a hard spending cap. The code runs under robot identities with minimal permissions and no keys. A first ADK agent already talks to Gemini 3.8 Flash on Agent Platform. **Phase 1 has started:** the database that will hold the manuals is running (on a free 30-day trial), and its tables, Spanish search and permissions are live. The catalog is loaded: 9,054 passages from 10 manuals, each with a Google embedding.

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
- **Schema (code in `infra/sql/`):** two tables (`catalog_chunks` = small passages that search ranks; `catalog_parents` = whole sections the agent reads), a vector index (HNSW) and a Spanish keyword index (GIN). "baterías" is stored as `bat`, so singular and plural match.
- **Least privilege, proven:** connecting *as* each robot, everyone can read, only `sg-ingestion` can write, and `sg-agent` gets "permission denied". A tricked agent can't alter the catalog.
- ⚠️ **Never click "Upgrade"** on the trial. It ends around 16 November by stopping; it never starts charging. Reminder set for 10 November.

### 6. The catalog and the embedding model (SMO-11 · ADR-005)
- **What:** you exported the two tables from n8n's Supabase. We re-embedded every passage with Google and loaded it into Cloud SQL as `sg-ingestion`, the only identity allowed to write. Result: 9,054 chunks, 1,171 sections, 0 orphans.
- **How we chose the model:** a benchmark, not a guess. Both candidate models embedded the full catalog, then we checked the 17 eval questions: is the right manual first? **`gemini-embedding-2`: 16/17. `gemini-embedding-001`: 13/17** (it mixes up sibling Polar manuals).
- **Gotcha worth remembering:** `gemini-embedding-2` returns *one* vector for a *list* of texts. Sending batches would have silently merged passages and ruined search. The script now checks this and fails loudly.

### 7. The search tool (SMO-12 · ADR-005 addendum)
- **What:** the n8n one-query hybrid search, ported 1:1 as a Python tool (`agent/storegear/tools/search.py`). It does vectors + Spanish keywords + rank fusion + the staff/manager filter, and returns the top 5 sections wrapped in `<manual>` tags (anti-prompt-injection "spotlighting").
- **Result, run as `sg-agent`:** right manual first **17/17**, all needed manuals in the top 5 **16/17**, search **~0.6 s** (n8n: 1.33 s). Staff never sees the managers' manual.
- **What we learned by measuring:** only 2–3 % of passages name their product, so we now embed the section header *with* the text (contextual embeddings). That took right-manual-first from 15/17 to 17/17.
- **Honest gap:** comparison questions ("A vs B") need one search per product. The agent will do that (SMO-13), and the eval checks it (SMO-14).

### 8. The StoreGear agent (SMO-13 · ADR-006)
- **What:** the real agent in ADK (`agent/storegear/`). Your n8n system prompt is copied word for word (rules 1–12). Two read-only tools: the hybrid search and **live price/stock from your Google Sheet**, which is shared with the robot as Viewer. **Pre-retrieval** searches before the first model call, as in n8n. The model is Gemini 3.8 Flash with low thinking.
- **First answers, run as the robot:** spec ✅ · comparison ✅ (it searched the second product on its own, closing the gap from SMO-12) · price 229 € / 7 in stock ✅ · out of catalog "no tengo esa información" ✅ · ambiguous "el Garmin" → asks which model ✅.
- **Where the prompt lives:** a file in git, reviewed with the code and gated by the eval, instead of Langfuse (a third-party service).
- **To watch:** latency 5–23 s locally and cold; measured properly in SMO-14 and SMO-15.
- **Try it yourself:** `uv run python agent/ask.py "tu pregunta"` shows every step and its timing.

### 9. The eval gate (SMO-14 · ADR-007)
- **What:** the same 22 questions, the same two LLM judges (copied from Langfuse) and the same judge model as n8n, so the comparison is fair. Script: `uv run python eval/run_eval.py`.
- **First run failed the gate:** correctness 4.77. In three answers the agent stopped one search too early: two "how do I…" answers didn't say how to open the menu, and one missed the "30 m" spec.
- **Tried and rejected:** medium thinking fixed it but was 6× slower.
- **What passed:** clearer guidance in the pre-retrieval block, plus a **timeout and retry** on model calls. The EU endpoint sometimes queues a call for 30–190 s; now slow calls are re-sent after 15 s.

| | Google Cloud | n8n |
|---|---|---|
| Correctness | **4.95** | 5.00 |
| Faithfulness | **4.91** | 4.95 |
| Context / Answer relevance | **5.00 / 5.00** | 5.00 / 5.00 |
| Median answer time | **6.2 s** | 9.0 s |

## What's next
| Next | Issue | What happens |
|---|---|---|
| 1 | SMO-15 | Deploy to Agent Runtime (or Cloud Run) and measure latency and cost. That completes Phase 1 (due 21 Oct) |

## Numbers to beat (n8n, 2026-10-11)
Correctness 5.00 · Faithfulness 4.95 · Context 5.00 · Answer 5.00 · median 9.0 s · ~$0.008 per answer.
