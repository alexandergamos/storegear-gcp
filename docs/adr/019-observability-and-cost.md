# ADR-019 — Observability and cost per answer: Google's own traces, one log line per answer, priced from its tokens

- **Status:** Accepted (2026-10-24, Alexander: option A)
- **Date:** 2026-10-24
- **Linear:** SMO-25 (tracing), SMO-26 (cost per answer)
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
In production today the Google Cloud build has structured logs for failures only (`AGENT_FAILED`). There is no trace of what happened inside an answer (guardrails, searches, model calls, how long each took) and no cost per answer: the only measured cost is the model's, $0.0055, from the eval's tokens at list price. Model Armor, the topic check and the embeddings are not counted.

The n8n build answers both questions with Langfuse: a trace per question with tokens, real cost and latency per step (the screenshot on the web demo). The rubric's top grades ask for monitoring, and the threat model has two open controls that belong here: "no PII in logs and traces" (LLM02) and "cost per answer + alerts" (LLM10).

Constraints:
- **No raw questions or personal data** in logs or traces (CLAUDE.md, ADR-015). Masked text may reach the model; it must not be stored by observability.
- **The goal of this build is Google Cloud end to end**; a third-party tool is a choice to justify, not a default.
- **Each answer must say which prompt and code produced it** (ADR-006: the prompt version is the deployed commit).
- Agent Platform has its own observability for Agent Runtime: traces in Cloud Trace (model calls, tool calls, latency, tokens) that can be switched on **without capturing prompt and response text**.

## Options considered
| Option | Pros | Cons | Cost (rough) |
|---|---|---|---|
| **A. Google-native (recommended):** Agent Runtime telemetry to Cloud Trace with message content off; one `ANSWER` log line per answer in `sg-api` (no text: ids, steps and their times, tokens, model, release, estimated cost); log-based metrics, a Cloud Monitoring dashboard and alerts; cost reconciled against the billing export in BigQuery | Everything stays in the project and under its IAM; nothing new to buy or run; text never stored; the same log line feeds latency, errors and cost; the billing export proves the estimate | Two places to look (Cloud Trace for one answer's inside, Monitoring for trends); the per-answer cost is an estimate from tokens × list price until the export confirms it; Cloud Trace's UI is less made for LLMs than Langfuse | Cloud Trace: first 2.5 M spans/month free; Logging: first 50 GiB/month free; BigQuery export: cents |
| B. Langfuse for Google Cloud too (OpenTelemetry exporter) | The same tool for both builds: a side-by-side comparison in one screen; an LLM-made UI with cost built in | Answers' metadata leave Google Cloud for a third party; ADK sends prompt text unless every exporter is configured not to; one more service and secret to run; works against "Google Cloud end to end" | Langfuse Hobby: free up to its limits |
| C. Billing export only | No code: Google's own invoice, by service | No per-answer number, no latency or step view, no alerts per question: it answers "how much this month", not "what did this answer cost and why" | Cents |

## Decision
**A**, in four pieces:

1. **Traces of the agent (SMO-25).** Redeploy the agent with Agent Runtime telemetry on and message content capture **off**, so Cloud Trace shows each answer's model calls, tool calls (`buscar_catalogo_hibrido`, `consultar_precio_stock`), latency and tokens, with no text. Checked by opening one trace and confirming it holds no prompt or answer.
2. **One `ANSWER` line per answer in `sg-api` (SMO-25 + SMO-26):** `event`, `agent` (gcp / n8n), conversation id, a 16-character hash of the user id (not the id), role, steps with their times, `total_ms`, guard outcome, `tokens_in` / `tokens_cached` / `tokens_out` / `model_calls` (summed from Agent Runtime's `usage_metadata`), model, `release` (the commit the CI deployed, `STOREGEAR_RELEASE`), `cost_eur` and `cost_usd`. Never the question or the answer: a unit test fails if either appears in the line (`api/tests/test_answer_log.py`).
3. **Cost per answer (SMO-26):** `api/cost.py` prices fresh input, cached input and output tokens (thinking counts as output) plus the topic check, at the rates **this project is billed**, read from the billing export (EUR, 2026-10-24: Gemini 3.8 Flash Regional EU €1.452 / €0.145 cached / €7.26 per million tokens). Model Armor doesn't appear in the bill (free allowance) and a query embedding is ~€0.000004, so both are left out. `eval/cost_report.py` compares the sum of `cost_eur` with the billed Gemini SKUs over a period; more than 15 % apart means the table is wrong. The bill also holds eval runs, so compare weeks without evals.
4. **Dashboard and alerts** (`infra/monitoring/`): log-based metrics `sg_answers`, `sg_answer_latency_ms`, `sg_answer_cost_eur`, `sg_agent_failures`; a Cloud Monitoring dashboard (answers and failures per hour by agent, p50/p95 latency, median cost per answer, guardrail stops by reason); an email alert at 3+ failed answers in an hour. At this volume a fixed count is clearer than a rate. Spending is already capped and alerted by the project budget (ADR-001), so no second cost alert.

## Consequences
- **Good:** the monitoring gap in the rubric closes with Google's own tools; every answer can be traced and priced; the threat-model items LLM02 (no PII in traces) and LLM10 (cost + alerts) close; the release in each line ties an answer to its commit.
- **Bad / accepted trade-offs:** cost per answer is an estimate checked weekly, not an exact meter; looking at one answer means opening Cloud Trace, looking at trends means Monitoring; the two builds are monitored with different tools (Langfuse vs Google), which the web demo will say plainly.
- **Caveats and gotchas:** the Agent Runtime telemetry switch is an environment variable at deploy time (`GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY`) or `AdkApp(enable_tracing=...)`, depending on the SDK; our deploy script already found that the runtime reserves some `GOOGLE_CLOUD_AGENT_ENGINE_*` variables, so the first deploy checks which one takes effect. Content capture (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`) must stay unset or false. The billing export only covers data from the day it is switched on, and it is enabled in the console (Billing → Billing export), not with gcloud.

## Revisit when
- A second agent or several teams share the project: an LLM-specific tool (Langfuse self-hosted on Cloud Run, or Agent Platform's own evaluation views) earns its cost.
- The estimate and the bill keep differing: meter cost from the billing export only.
- Volume makes Cloud Logging pricier than the free tier: sample traces, keep the `ANSWER` line for every answer.

## Learn more
- Trace an agent on Agent Runtime: https://docs.cloud.google.com/agent-builder/agent-engine/manage/tracing
- Log-based metrics: https://cloud.google.com/logging/docs/logs-based-metrics
- Export Cloud Billing data to BigQuery: https://cloud.google.com/billing/docs/how-to/export-data-bigquery
- Gemini pricing on Agent Platform: https://cloud.google.com/vertex-ai/generative-ai/pricing
