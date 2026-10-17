# StoreGear on Google Cloud — context for Claude Code

The StoreGear Assistant (master's MVP, Alexander, Barcelona) is being rebuilt **entirely on Google Cloud** with ADK + Vertex AI. The original agent runs on n8n Cloud; that build is the official deliverable. This repo is the extra challenge, due **31 Oct 2026**.

**Main goal: learning.** Alexander wants to understand, like an AI engineer shipping a product to production, what each component is, why it was chosen, the alternatives, pros and cons, caveats and cost. Shipping without understanding counts as failure.

## Where things live
| Path | What |
|---|---|
| `agent/` | ADK agent (prompt, tools, callbacks) |
| `ingestion/` | PDF → parse → chunk → injection check → embeddings → Cloud SQL |
| `eval/` | 22-question dataset, LLM judges, comparison vs the n8n baseline |
| `infra/` | gcloud scripts (Terraform later, see ADR-001) |
| `docs/adr/` | Decision records. **One per significant choice, written before the code.** |
| `docs/build-log.md` | Bilingual (EN/ES) diary. **One entry per Linear issue closed.** |

The reference implementation is the n8n repo `C:\Users\alexg\GitHub\smoothr-storegear-n8n` (`CLAUDE.md`, `docs/storegear-backlog.md`, `docs/storegear-workflow-explained.md`). Read the matching section before porting a component.

## How we work (AI product team)
- **Planning:** Linear project "StoreGear on Google Cloud" (team Smoothr, SMO-6 to SMO-32), with one milestone per phase. Every piece of work has an issue, and its number goes in commit messages (`SMO-12: ...`).
- **ADR first:** before building a component, draft its ADR (`docs/adr/template.md`), covering options, pros and cons, caveats, cost and when to revisit. Alexander decides, and the ADR status changes from Proposed to Accepted.
- **Teach while building:** explain the why, not just the what. Name the concept, the alternative, the trade-off, and what would make us choose differently. Point to the official docs.
- **Alexander runs infrastructure steps himself** (gcloud, IAM, deploys, console). Give him the commands with an explanation; don't run them silently. Claude Code writes most of the application code, and Alexander reviews it.
- **Ask before deciding:** when there are real options, give a multiple choice with a recommended option.
- **Progress diagram:** after closing an issue, update its status in `docs/diagram/build_progress_diagram.js`, regenerate (`node docs/diagram/build_progress_diagram.js`, then `render_png.js` for the PNG) and refresh `docs/progress.md`.
- **Eval gate:** every phase ends with the 22-question eval against the n8n baseline. A phase isn't done until the eval passes.
- **Keep it simple:** production-grade but no gold-plating. If time runs out, stop at the last green phase.

## Baseline to match (n8n, 2026-10-11)
Correctness 5.00 · Faithfulness 4.95 · Context relevance 5.00 · Answer relevance 5.00 · median latency 9.0 s · ~$0.008 per answer.

## Security rules (non-negotiable)
- No secrets in code, docs, commits or chat. Use Secret Manager, plus Application Default Credentials locally. **Never create service-account JSON key files.**
- Least-privilege service accounts; never use Owner or Editor roles for runtime identities.
- The role (staff/manager) comes only from the verified token, never from the LLM.
- PII is masked before the model, memory, logs and dead-letter queue. Logs never contain raw questions.
- No outbound or action tools without a human-in-the-loop step (keeps the lethal trifecta broken).
- A budget alert exists on the project. Eval runs cost money, so run them deliberately.

## Stack (planned, each piece confirmed by its ADR)
Python 3.12 + uv · ADK 2.x · **Gemini Enterprise Agent Platform** (the evolution of Vertex AI since Apr 2026: Gemini models, Agent Runtime, Agent Sessions + Memory Bank, Agent Evaluation, Agent Observability, Agent Identity / Gateway + Model Armor) · Cloud SQL Postgres + pgvector · Document AI · Secret Manager · Cloud Run (alternative runtime) · Cloud Build or GitHub Actions.
Older docs and URLs still say "Vertex AI" / "Agent Engine": same products, new names. Check the current docs (docs.cloud.google.com/gemini-enterprise-agent-platform) before relying on memory, and check europe-west1 availability in every ADR.
