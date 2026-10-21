# ADR-014 — Authentication: Identity Platform tokens verified by a thin API on Cloud Run; the role comes only from the token

- **Status:** Accepted (2026-10-21)
- **Date:** 2026-10-21
- **Linear:** SMO-22 (planned as "ADR-012"; renumbered)
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
The threat model's top open gap (ADR-013, ASI03/LLM02): **today whoever calls the agent sets the role** in the session state. The role filter in SQL is correct, but a caller who writes `manager` gets manager data. Today only Google principals can call Agent Runtime (Alexander, and service accounts with Agent Platform User), so nobody outside can reach it, but shop staff can't use it either: they aren't Google Cloud principals.

We need: (1) only authenticated employees reach the agent, (2) the role comes from a **verified token**, never from the request body or the model, (3) allowed origins (CORS) and **per-user rate limiting**, (4) tests for 401 / 403 / staff / manager. The n8n build had a JWT-protected webhook with a self-signed token; a "real identity provider" was its open backlog item (B1).

Facts that shape the options (checked 2026-10-21):
- The project is **not in an organization** (personal account). IAP's direct mode on Cloud Run (no load balancer) requires an organization and users from it, so it's ruled out.
- Identity Platform: the first **50,000 monthly active users are free** for email/password, phone and social sign-in; OIDC/SAML (tier 2) only 49 free.

## Options: who issues and verifies identity

| | **A. Identity Platform + thin API on Cloud Run (chosen)** | B. Firebase Auth + same API | C. IAP | D. API Gateway | E. Self-signed JWT (as in n8n) |
|---|---|---|---|---|---|
| What it is | Google's customer identity service; signs ID tokens; custom claims for the role | Same engine, consumer tier | Proxy that authenticates before the request reaches the app | Gateway that validates JWTs and quotas per API key | Our own secret signs tokens |
| User management | Console + Admin SDK: create users, disable, reset, MFA | Same, fewer enterprise features (no SLA, no multi-tenancy, no blocking functions) | Google accounts of an organization, or Identity Platform behind a load balancer | None (needs an IdP anyway) | None: we'd build it |
| Role | Custom claim `role` set by an admin script | Same | IAM groups (needs Cloud Identity/Workspace) or claims | Passed through from the IdP | Our claim |
| Fit here | ✅ No organization needed; free at our size; standard OIDC JWT | ✅ but A is the same with the enterprise options open | ❌ direct mode needs an organization; LB mode adds ~$18+/month and still needs A | ➖ extra component; per-user limits still in the app | ❌ we'd own user management and a signing secret |

## Decision

```
client (web app later; eval and curl now)
  │  Authorization: Bearer <Identity Platform ID token>
  ▼
Cloud Run service sg-api (europe-west1, runs as NEW service account sg-api)
  1. verify the token: signature (Google public keys), issuer, audience = project, expiry      → 401 if not
  2. role = custom claim "role" ∈ {staff, manager}                                                → 403 if missing
  3. per-user rate limit (uid): 20 requests/min, 300/day, counters in Cloud SQL                   → 429 if over
  4. CORS: only the allowed origins list
  5. call Agent Runtime AS sg-api: session user_id = uid, state user:role = role (from the token)
  ▼
Agent Runtime (unchanged agent; reads the role from state as today)
```

1. **Identity Platform** with **email/password** for shop staff (Google sign-in can be added later). Users are created and the `role` claim is set **only by an admin script run by Alexander** (`infra/users.py`), never by the app.
2. **`sg-api`**: FastAPI on Cloud Run, a new service account `sg-api` with only Agent Platform User + Cloud SQL Client/Instance User (rate-limit table) + Logs Writer. The browser never talks to Agent Runtime.
3. **Rate limiting in the app, per user**, in a Cloud SQL table (a fixed-window counter per uid). Cloud Run's max instances stays the global cap. Edge protection by IP (Cloud Armor) needs a load balancer: noted, not built (see *Revisit*).
4. **Who can call the agent directly** after this: Alexander (owner) and the service accounts with Agent Platform User. `sg-ingestion` keeps that role for Gemini, which also allows querying the agent: accepted, it's our own job, never an end user. The default Compute account still holds **Editor**: removing it is deferred to SMO-28, because in new projects Cloud Build builds images with that account; CI/CD gets its own build service account first, then Editor goes.
5. **Tests** (`eval/auth_tests.py`): no token → 401 · bad or expired token → 401 · valid token without role → 403 · staff asking for internal margins → only public sections · manager → internal document · 21st request in a minute → 429. The 22-question eval moves to calling `sg-api` with a staff test user.

## Caveats
- **Where Identity Platform stores accounts:** it's a global service; check the data-location settings in the Console. The data is minimal (work email, uid, role).
- **Token lifetime:** ID tokens last 1 hour and refresh automatically on the client; disabling a user takes effect at the next refresh (up to 1 h). For an immediate cut, `sg-api` can check revocation (an extra call per request): noted, off by default.
- The web front end is out of scope (SMO-22 delivers the authenticated API and its tests).

## Consequences
- **Good:** the role can no longer be chosen by the caller; standard tokens (any future app or MCP client can use them); free at our size; 401/403/429 behaviour testable.
- **Bad / accepted:** one more service to run (`sg-api`); rate limits per Cloud SQL round trip (a few ms); no IP-level DDoS protection without a load balancer.

## Addendum (2026-10-21): built and tested
- Identity Platform with **Email/Password only**; **sign-up disabled** (only `infra/users.py` creates accounts and roles). The auto-created API key is restricted to **Identity Toolkit API + Token Service API** (Firebase had left it open to ~25 APIs, including Cloud SQL Admin and Cloud Logging).
- `sg-api` on Cloud Run (europe-west1, service account `sg-api`, public access because authentication is in the app, max 2 instances, concurrency 10, timeout 300 s, no OpenAPI route).
- **`eval/auth_tests.py`: 7/7** against the deployed service: no token 401 · garbage token 401 · no role 403 · staff gets no internal figures ("No tengo esa información…", without revealing the document exists) · manager gets supplier cost 268 € and margin 33 % · `"role": "manager"` in the body is ignored · exhausted daily quota 429.
- Lessons: Cloud Run's front end **reserves paths ending in "z"** (`/healthz` → 404; now `/health`); the Cloud SQL connector needs the `cloud-platform` scope as well as `sqlservice.login`.
- Pending for SMO-28: the 22-question eval through `sg-api` (staff test user); removing Editor from the default Compute account once CI has its own build account.

## Revisit when
The agent is exposed publicly at scale (→ external HTTPS load balancer + Cloud Armor rate limiting by IP); the shop gets a Google Workspace organization (→ IAP in front of `sg-api`, role from groups); or staff need single sign-on with another IdP (→ OIDC/SAML provider, tier-2 pricing).
