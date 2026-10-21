# ADR-016 — Sessions and retention: Agent Platform Sessions with a 30-day TTL, no long-term memory, history without the model

- **Status:** Proposed (2026-10-21)
- **Date:** 2026-10-21
- **Linear:** SMO-24 (planned as "ADR-014"; renumbered)
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Each employee needs their own conversations, so follow-up questions work ("¿y tiene stock?"), and the right to see and delete them. Conversations are personal data (what staff type, with PII masked since ADR-015), so they need a **retention limit** (GDPR storage limitation): 30 days, as in n8n.

**What we found (2026-10-21):** sessions already live in **Agent Platform Sessions** (`eu`, ADR-008), but **every session expires after 365 days by default**: the 100+ sessions stored today (evals and tests) expire in October 2027. Sessions accept a `ttl` (or `expire_time`) at creation; at expiry the session and its events are deleted by the platform. ADK already refuses to return or delete a session whose `user_id` doesn't match the caller's.

## Options

**Where sessions live**
| | **A. Agent Platform Sessions (chosen, already in use)** | B. ADK `DatabaseSessionService` on Cloud SQL | C. In-memory |
|---|---|---|---|
| Retention | Native per-session TTL; deletion by the platform | Our own job (SQL delete) | Lost on restart |
| Isolation | `user_id` checked by ADK on read and delete | Ours | — |
| Ops / cost | Managed, `eu`, no schema | Tables + migrations + backups; ties sessions to the Cloud SQL trial decision | — |

**Long-term memory (Memory Bank)**
Memory Bank would extract "facts" from conversations and recall them across sessions. **Not enabled:** staff ask about the catalog, not about themselves, so it adds little; it would turn conversations into longer-lived personal profiles; and ADR-013 requires per-user scoping and a review before enabling it.

## Decision (proposed)
1. **Sessions stay in Agent Platform Sessions**; `sg-api` creates every session with **`ttl = 30 days`**; eval and test scripts with **1 day**.
2. **Retention audit** (`infra/sessions_retention.py`): lists every session, deletes those older than 30 days and shortens any longer expiry to 30 days from creation. Run once now (fixes the 365-day sessions) and on a schedule from SMO-28. The TTL is the mechanism; the audit is the proof.
3. **History without the model**, in `sg-api` (role and identity from the token, as always):
   - `GET /sessions`: the caller's own sessions (id, last update, expiry).
   - `GET /sessions/{id}`: the messages of one session (text only); no LLM call.
   - `DELETE /sessions/{id}`: the employee deletes their own conversation (right to erasure).
4. **Isolation tests** (`eval/session_tests.py`): a follow-up works in the same session; history loads in well under a second; another user gets **404** for the same session id (read, delete and chat); a new session expires 30 days after creation.

## Consequences
- **Good:** retention enforced by the platform; nothing new to run; the right to see and erase is built in; no long-lived profiles.
- **Bad / accepted:** a conversation older than 30 days is gone, even if an employee wanted it; no cross-session personalisation.

## Revisit when
Staff need personal preferences remembered across sessions (→ Memory Bank, scoped per user, with its own retention and a threat-model review), or the legal retention period changes.
