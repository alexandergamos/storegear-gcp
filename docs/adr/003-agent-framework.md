# ADR-003 — Agent framework: ADK on Gemini Enterprise Agent Platform

- **Status:** Accepted (2026-10-16)
- **Date:** 2026-10-16
- **Linear:** SMO-9
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
In n8n, the "agent" was the AI Agent node: a model, a system prompt, tools wired as sub-workflows, and memory as a node. In code, a **framework** plays that role. It runs the loop (prompt → model → tool call → result → model …), turns Python functions into tools, keeps session state, and offers hooks (callbacks) for guardrails.

ADR-000 sets the constraint: Google Cloud only, and learning matters as much as shipping.

## Options considered
| Option | What it is | Pros | Cons |
|---|---|---|---|
| **ADK (Agent Development Kit) 2.x** | Google's open-source, code-first framework; the code path inside Agent Platform | Native to Agent Runtime, Sessions, Memory Bank, Evaluation and Observability; `adk web` dev UI; `adk eval`; callbacks for guardrails; Python | Google-centric conventions; v2 is recent (GA May 2026), so some examples online are v1 |
| Agent Studio / Managed Agents API | Low-code or agent-as-a-service on the same platform | Fastest to a working agent | Hides the loop, tools and state: the opposite of the learning goal. Some governance features still "coming soon" |
| LangGraph | Graph-based framework from LangChain | Very flexible; big community | Not native to Agent Platform services; more glue code |
| OpenAI Agents SDK | OpenAI's lightweight framework | Simple | Built around OpenAI models; off-target for Google Cloud only |
| Plain Gemini function calling (google-genai SDK) | Write the loop ourselves | Maximum understanding | We'd rebuild sessions, eval and tracing by hand; doesn't fit 15 days |

## Decision
**ADK 2.x (Python 3.12, managed with uv)**, with models served by Agent Platform through Application Default Credentials. No AI Studio API key.

## Consequences
- **Good:** one framework from local dev (`adk web`) to production (Agent Runtime). The Agent Platform services plug in instead of being built by hand.
- **Bad / accepted:** coupling to Google's agent stack. Mitigation: tools are plain Python functions and the prompts are files, so both are portable.
- **Caveats:**
  - Tool docstrings and type hints become the tool description the model reads. Write them like prompts.
  - `adk web` is for development only, never production.
  - Some Gemini models (especially previews) may only be served on the `global` endpoint, not `europe-west1`. SMO-9 tests which models answer in europe-west1 and records the result here.

## Verified (SMO-9, 2026-10-16)
ADK 2.12.0 on Python 3.12.15 (uv). The `hello_agent` loop works end to end through Application Default Credentials, with no API key: tool call → tool result → answer, about 7 s for two model calls on `gemini-3.8-flash` via the `eu` endpoint. The model endpoint decision is in ADR-001's addendum.

## Revisit when
Agent Platform features we depend on aren't available in europe-west1, or we need multi-cloud portability.

## Learn more
- ADK: https://adk.dev
- Python quickstart: https://adk.dev/get-started/python/
- Gemini Enterprise Agent Platform: https://docs.cloud.google.com/gemini-enterprise-agent-platform
