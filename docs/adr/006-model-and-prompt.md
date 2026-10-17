# ADR-006 — Model settings and prompt management

- **Status:** Accepted (2026-10-17)
- **Date:** 2026-10-17
- **Linear:** SMO-13
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
The n8n agent used Gemini 3.8 Flash through OpenRouter with low reasoning effort. Its system prompt (rules 1–12) lived in **Langfuse Prompt Management** with production/staging labels and a hard-coded fallback copy in the node. On Google Cloud we need equivalents for:
1. model and generation settings;
2. where the prompt lives and how a change is released and rolled back;
3. pre-retrieval (search before the first model call), the latency win from n8n D4.

## Options considered

### Prompt management
| Option | Pros | Cons |
|---|---|---|
| **Versioned file in git** (`agent/storegear/prompts/system_es.md`) | Reviewed in PRs next to the code that depends on it; the eval gate (SMO-28) runs on every change; rollback = git revert; no extra service | A prompt change needs a deploy; non-developers can't edit it |
| Langfuse (as in n8n) | Label-based releases without a deploy; non-dev editing | A third-party service outside Google Cloud (breaks ADR-000); a runtime dependency with a fallback copy to maintain |
| Agent Platform prompt management | Google-native; console editing | Another API dependency at runtime; ties releases to a console action that's harder to gate on the eval |

### Model and settings
| Setting | Choice | Why |
|---|---|---|
| Model | `gemini-3.8-flash` via the `eu` endpoint | Same as the n8n baseline (fair comparison); EU processing (ADR-001 addendum) |
| Thinking | `thinking_level=low` | Mirrors n8n's low reasoning effort, which halved latency there with no score loss |
| Temperature | 0.2 | Factual answers from manuals; little creativity needed |

## Decision
- **The prompt is a versioned file in git**, copied verbatim from the n8n fallback (5,808 chars, rules 1–12 plus response format). It's loaded once at start-up. Release = merge + deploy, gated by the 22-question eval. The prompt version recorded with each answer = the deployed commit (SMO-25).
- **Pre-retrieval** is implemented as an ADK `before_model_callback`. On the first model call of each turn it searches the user's message and appends the top 5 sections plus the n8n "COMO USARLA" guidance to the system instruction. The block is cached per invocation, so it runs once per turn.
- **Tools:** `buscar_catalogo_hibrido` and `consultar_precio_stock`, same names and contract as n8n. Both are read-only. **The role comes from session state** (`user:role`, set by the verified login in SMO-22), never from a tool argument.
- **Model:** `gemini-3.8-flash`, thinking low, temperature 0.2, all overridable by env vars for experiments.

## Verified (2026-10-17, `agent/ask.py`, as sg-agent)
| Question | Behaviour | Result |
|---|---|---|
| Q1 spec | Answered from pre-retrieval, no extra search | ✅ 10 ATM / 100 m, source cited |
| Q16 comparison | Pre-search had one product → **searched the other one** (guidance rule c) | ✅ table, Instinct 100 m vs Vantage M2 30 m |
| Q18 price/stock | fileId from pre-search → live Sheet | ✅ 229 €, 7 in stock, "tiempo real" |
| Q19 out of catalog | No search needed | ✅ "No tengo esa información…" |
| Q20 ambiguous | Asked which Garmin model | ✅ |

Latency was 5–23 s locally, cold. Measured properly in SMO-14 and SMO-15.

## Consequences
- **Good:** behavioural parity with n8n from day one. The prompt and code are reviewed together. One fewer external service.
- **Bad / accepted:** no "edit the prompt in a web UI" workflow. Prompt experiments are branches plus eval runs.
- **Caveats:**
  - Pre-retrieval adds ~20k characters of context to every turn, including ones that don't need it (greetings, ambiguous questions). That costs tokens; watch it in the cost report (SMO-26).
  - Rule 9 forbids revealing `fileId`, yet the tags expose it to the model. That's accepted, as in n8n.

## Revisit when
- Non-developers need to tune the prompt: consider Agent Platform prompt management with an eval-gated promotion step.
- The cost report shows pre-retrieval tokens dominating: skip it for very short or obviously non-product messages.

## Learn more
- ADK callbacks: https://adk.dev
- Gemini thinking configuration: https://docs.cloud.google.com/gemini-enterprise-agent-platform
