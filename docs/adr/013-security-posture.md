# ADR-013 — Security posture: defence in depth, trifecta kept broken, risks owned in the threat model

- **Status:** Proposed (2026-10-21)
- **Date:** 2026-10-21
- **Linear:** SMO-21 (planned as "ADR-011"; renumbered: 011 and 012 went to ingestion orchestration and Drive sync. SMO-22 auth → ADR-014, SMO-23 guardrails → ADR-015)
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Phase 3 adds authentication, guardrails, PII handling and memory. Before building defences we need to know what we defend (assets), from whom (actors), through where (entry points) and which risks we accept. The full analysis is in [`docs/threat-model.md`](../threat-model.md), reviewed against the OWASP Top 10 for LLM Applications 2025 and the OWASP Top 10 for Agentic Applications (Dec 2025).

## Decision (proposed)
1. **Defence in depth, five layers.** No single control is trusted alone:
   | Layer | Controls |
   |---|---|
   | Identity and access | IAM least privilege, no keys, role from a verified token (SMO-22), rate limits |
   | Data | Role filter inside the search SQL; injection gate + quarantine at ingestion; Drive as the only source |
   | Model | Spotlighting tags; prompt in git; Model Armor on user input; Gemini safety settings (SMO-23) |
   | Output | Plain-text rendering; links and phones only from cited sections; PII masking (SMO-23) |
   | Operations | Budget cap, bounded retries, alerts, PII-free logs, retention (SMO-24/25/27) |
2. **Access control never lives in the prompt.** The model is not asked to hide anything; what a role may see is decided in SQL and IAM before the model sees it.
3. **The lethal trifecta stays broken.** The agent has private data and untrusted content, but **no tool that sends, writes or fetches externally**. Adding one requires a human approval for each action (HITL) and a new review of the threat model.
4. **Every risk is owned.** Each OWASP item in the threat model has a control (built, or planned with its issue) or an accepted-risk note with the reason. A new feature updates the threat model in the same PR.

## Consequences
- **Good:** the remaining Phase 3 issues get a clear order (SMO-22 first: today the caller sets the role); the thesis comparison gets an explicit security baseline; accepted risks are written down rather than forgotten.
- **Bad / accepted:** some risks stay accepted (prompt leakage, vendor misinformation, embedding inversion of public manuals), each with its reason; the HITL rule slows down any future "action" feature by design.

## Revisit when
A tool that acts or sends data outside is proposed; Memory Bank is enabled; the agent is exposed via MCP/A2A (SMO-31); or OWASP publishes a new edition (re-map the tables).
