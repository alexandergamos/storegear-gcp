# sg-api comparison mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add to `sg-api` everything the StoreGear web demo needs: a public model list, a demo-only `/compare` stream that asks both agents in parallel (blind A/B), votes, the end-of-conversation reveal, and a streamed single-agent `/chat/stream`.

**Architecture:** `sg-api` stays the single door (spec §5, approach A). New logic lives in small modules next to `api/main.py`: agent adapters (`agents.py`), step/stream assembly (`stream.py`), persistence (`store.py`), display names (`catalog.py`). Both agents are behind one interface so tests use fakes; the A/B mapping never leaves the server until `/reveal`.

**Tech Stack:** Python 3.12, FastAPI, pytest + FastAPI `TestClient`, `httpx` (n8n calls; `MockTransport` in tests), `PyJWT` (HS256 token for n8n), pg8000 via Cloud SQL Connector (existing), Server-Sent Events over a `StreamingResponse`.

**Spec:** `C:\Users\alexg\GitHub\storegear-web\docs\superpowers\specs\2026-10-22-storegear-web-design.md` (sections 5-7).

## Global Constraints

- Agent Platform access is restricted: **all tests use fakes**; no test calls Google or n8n. Live checks are the last task and are run by Alexander's go-ahead.
- Existing endpoints and their JSON contracts stay unchanged (`/chat`, `/sessions*`, `/health`): `eval/auth_tests.py`, `eval/guardrail_tests.py`, `eval/session_tests.py` depend on them.
- Role and demo flag come **only** from the verified token (`role` ∈ {staff, manager}; `demo` is `True` only if the claim is literally `true`).
- `/compare` requires `demo: true` → otherwise **403** `"demo only"`. A compare counts as **one** call to `rate_limit()`.
- The mapping (which slot is `gcp`, which is `n8n`) is drawn **once per conversation** and is **never** in any `/compare` or `/vote` response; only `/conversations/{id}/reveal` returns it.
- In `/compare` streams, `step` events carry **no** `ms` field; `answer` events carry `total_ms` (real for both agents). `/chat/stream` step events **do** carry `ms`.
- Step labels, exact strings: `Pregunta revisada`, `Buscando en los manuales`, `Consultando precio y stock`, `Redactando la respuesta`.
- Error text shown for a failed slot, exact: `Este agente no ha podido responder ahora.`
- n8n call: `POST {STOREGEAR_N8N_URL}` (default `https://thebridge.app.n8n.cloud/webhook/storegear-agent`), body `{"message", "conversationId"}`, header `Authorization: Bearer <HS256 JWT>` with claims `sub` = uid, `role` = `"staff"`, `exp` = now + 60 s, secret from env `STOREGEAR_N8N_JWT_SECRET` (Secret Manager in Cloud Run). Response `{"output": str}`; `{"error": ...}` or non-200 = failure. Timeout 120 s.
- PII is masked with `guards.mask_pii` before the message goes to **either** agent.
- No secrets in code, logs or test fixtures (tests use the literal secret `"test-secret"`).

## API contract (shared with the web plan)

```
GET  /catalog/models                      public → {"models": ["Garmin Instinct 3 AMOLED", ...]}   (staff-level manuals only, sorted)
POST /compare        {message, conversation_id?}   demo only → text/event-stream:
     event: conversation  data: {"conversation_id": str}                      (first event, always)
     event: step          data: {"slot": "A"|"B", "label": str, "status": "running"|"done"}
     event: answer        data: {"slot": "A"|"B", "text": str, "total_ms": int}
     event: error         data: {"slot": "A"|"B", "message": "Este agente no ha podido responder ahora.", "total_ms": int}
     event: done          data: {"comparison_id": str, "votable": bool}
POST /compare/{comparison_id}/vote   {vote: "A"|"B"|"tie"} → {"ok": true}
     404 not yours/unknown · 409 already voted, conversation revealed, or not votable
POST /conversations/{conversation_id}/reveal → {"mapping": {"A": "gcp"|"n8n", "B": ...},
     "comparisons": [{"comparison_id", "question", "a_total_ms", "b_total_ms", "vote"}]}   404 not yours
POST /chat/stream    {message, session_id?}  any role → text/event-stream:
     event: step   data: {"label", "status", "ms"?}   (ms on "done")
     event: answer data: {"text": str, "total_ms": int, "session_id": str}
     event: error  data: {"message": str, "total_ms": int}
```

## Review Focus

1. **A question sent to a revealed conversation** → 409 `"conversation closed"`, no agent is called. (Task 7)
2. **One agent hangs past the n8n timeout / Agent Runtime timeout** → that slot gets `error` with its `total_ms`; the other slot's `answer` is not delayed; `done.votable` is `false`. (Task 6)
3. **A client that reads the network tab** → none of the strings `gcp`, `n8n` or `Google` appears in the metadata of a `/compare` or `/vote` response (fake agents in tests never produce them in answer text). (Task 7, Task 8)
4. **A guard block on the Google Cloud side** (Model Armor, off-topic) → that slot still gets a normal `answer` with the guard reply text (it's a valid answer to vote on), not an `error`. (Task 5)
5. **`conversation_id` of another user** → 404 on `/compare`, `/vote`, `/reveal` (never 403, so ids can't be probed). (Tasks 7, 8)

---

### Task 1: Test harness + demo claim + `/compare` auth gate

**Files:**
- Modify: `api/main.py` (`user()` returns `demo`)
- Create: `api/tests/conftest.py`, `api/tests/test_auth_gate.py`
- Modify: `pyproject.toml` (dev group: `pytest`, `httpx`; main: `pyjwt`)

**Interfaces:**
- Produces: `user()` → `{"uid": str, "role": str, "demo": bool}`. Fixtures: `client` (TestClient with `app.dependency_overrides`), `as_user(uid="u1", role="staff", demo=False)` that overrides `user`, `no_rate_limit` (monkeypatch `main.rate_limit` to a no-op counter list).

- [ ] **Step 1: Write the failing tests** `test_compare_requires_token` (no header → 401), `test_compare_requires_demo` (`as_user(demo=False)` → 403 `{"detail": "demo only"}`), `test_user_demo_claim_parsing` (monkeypatch `id_token.verify_firebase_token` to return `{"sub": "u1", "role": "staff", "demo": True}` → `demo is True`; `"demo": "true"` string → `False`).
- [ ] **Step 2: Run** `uv run pytest api/tests/test_auth_gate.py -v` → FAIL (no `/compare`, no `demo`).
- [ ] **Step 3: Implement** `demo = claims.get("demo") is True` in `user()`; add a stub `POST /compare` that depends on `user` and raises 403 `"demo only"` unless `who["demo"]`; `api/tests/conftest.py` sets `sys.path` to `api/` and env `STOREGEAR_N8N_JWT_SECRET=test-secret`.
- [ ] **Step 4: Run** the same command → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): demo claim and /compare auth gate (test harness)`.

### Task 2: Model display names + `GET /catalog/models`

**Files:**
- Create: `api/catalog.py`, `api/tests/test_catalog.py`
- Create: `infra/sql/009_web_demo.sql` (first part: `GRANT SELECT ON catalog_chunks TO "sg-api@storegear-prod-ag26.iam";`)
- Modify: `api/main.py`

**Interfaces:**
- Produces: `display_name(file_name: str) -> str`; `list_models(fetch_file_names: Callable[[], list[str]]) -> list[str]` (dedup, sorted); `GET /catalog/models` (no auth) using SQL `SELECT DISTINCT file_name FROM catalog_chunks WHERE access_level = 'staff' AND file_id <> 'polar-common'`; result cached in-process for 10 min.

- [ ] **Step 1: Failing tests** with the 9 current staff files, exact expectations:
  `"Instinct_3_AMOLED_OM_ES-XM.pdf"→"Garmin Instinct 3 AMOLED"`, `"Venu_X1_OM_ES-XM.pdf"→"Garmin Venu X1"`, `"Suunto_Ocean_UserGuide_ES.pdf"→"Suunto Ocean"`, `"Polar Ignite 2.pdf"→"Polar Ignite 2"`, `"Polar Grit X2.pdf"→"Polar Grit X2"`, `"Polar Vantage M2.pdf"→"Polar Vantage M2"`, `"Polar Vantage V2.pdf"→"Polar Vantage V2"`, `"Polar Pacer Pro.pdf"→"Polar Pacer Pro"`, `"Polar Grit X Pro.pdf"→"Polar Grit X Pro"`; unknown `"Foo_Bar_OM_ES-XM.pdf"→"Foo Bar"`; endpoint test: no auth → 200, never includes a name from a `manager` file (fake fetch returns only what the SQL would).
- [ ] **Step 2: Run** `uv run pytest api/tests/test_catalog.py -v` → FAIL.
- [ ] **Step 3: Implement** rules in order: drop extension; drop suffixes `_OM_ES-XM`, `_UserGuide_ES`; `_` → space; prefix `Garmin ` when the name starts with `Instinct`, `Venu`, `Fenix`, `Forerunner`, `Edge`; prefix `Suunto ` if missing and the file name started with `Suunto_` (already present → keep). Endpoint wires `list_models` to `db()`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): public model list with display names`.

### Task 3: Comparison store (SQL + store with a fake)

**Files:**
- Modify: `infra/sql/009_web_demo.sql` (tables + grants)
- Create: `api/store.py`, `api/tests/test_store.py`

**Interfaces:**
- Produces (Protocol `CompareStore`, implemented by `PgStore(db: Callable)` and `MemoryStore()`):
  - `create_conversation(uid: str, mapping_a: Literal["gcp","n8n"]) -> str` (uuid4 hex)
  - `get_conversation(conversation_id: str, uid: str) -> Conversation | None` (`None` if not this uid's) — `Conversation(id, uid, mapping_a, gcp_session_id: str | None, revealed: bool)`
  - `set_gcp_session(conversation_id: str, session_id: str) -> None`
  - `add_comparison(conversation_id: str, uid: str, question: str, a_total_ms: int, b_total_ms: int, a_error: bool, b_error: bool) -> str`
  - `vote(comparison_id: str, uid: str, vote: Literal["A","B","tie"]) -> Literal["ok","not_found","conflict"]`
  - `reveal(conversation_id: str, uid: str) -> dict | None` (sets `revealed_at`; returns the reveal payload of the API contract)
- SQL: `compare_conversations(id text pk, uid text not null, mapping_a text check (mapping_a in ('gcp','n8n')), gcp_session_id text, created_at timestamptz default now(), revealed_at timestamptz)`; `compare_votes(id text pk, conversation_id text references compare_conversations(id), uid text not null, question text not null, a_total_ms int, b_total_ms int, a_error bool, b_error bool, vote text check (vote in ('A','B','tie')), voted_at timestamptz, created_at timestamptz default now())`; `GRANT SELECT, INSERT, UPDATE ON compare_conversations, compare_votes TO "sg-api@storegear-prod-ag26.iam";`

- [ ] **Step 1: Failing tests on `MemoryStore`** (the contract both implementations follow): another uid → `get_conversation` `None`, `vote` `"not_found"`, `reveal` `None`; second vote → `"conflict"`; vote when `a_error` or `b_error` → `"conflict"`; vote after reveal → `"conflict"`; reveal returns `mapping` `{"A": mapping_a, "B": other}` and the comparisons in insertion order.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_store.py -v` → FAIL.
- [ ] **Step 3: Implement** `MemoryStore` (dicts) and `PgStore` (same semantics in SQL; `vote` uses one `UPDATE … WHERE id=%s AND uid=%s AND vote IS NULL AND NOT a_error AND NOT b_error AND conversation not revealed RETURNING id`, distinguishing not-found from conflict with a prior `SELECT`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): comparison store (SQL 009, Pg + memory)`.

### Task 4: n8n agent client

**Files:**
- Create: `api/agents.py` (n8n part), `api/tests/test_n8n_agent.py`

**Interfaces:**
- Produces: `n8n_token(uid: str, now: float) -> str`; `ask_n8n(message: str, uid: str, conversation_id: str, client: httpx.Client | None = None) -> str` (returns `output`; raises `AgentError` on non-200, `error` field, missing `output`, or timeout).
- Produces: `class AgentError(Exception)`.

- [ ] **Step 1: Failing tests:** token decodes with `"test-secret"` to `sub=uid`, `role="staff"`, `exp=now+60`, algorithm HS256; request body is exactly `{"message": m, "conversationId": c}` and carries `Authorization: Bearer <token>` (assert via `httpx.MockTransport`); 200 `{"output":"x"}` → `"x"`; 200 `{"output":"…","error":"invalid_request"}` → `AgentError`; 500 → `AgentError`; `httpx.TimeoutException` → `AgentError`.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_n8n_agent.py -v` → FAIL.
- [ ] **Step 3: Implement** with `jwt.encode`, `httpx.Client(timeout=120)`, URL from env.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): n8n agent client (server-signed HS256 token)`.

### Task 5: Google Cloud agent as a step stream (shared by `/chat`)

**Files:**
- Modify: `api/agents.py` (gcp part), `api/main.py` (`/chat` uses it; JSON contract unchanged)
- Create: `api/tests/test_gcp_agent.py`

**Interfaces:**
- Produces: `gcp_events(remote, uid: str, role: str, message: str, session_id: str | None, clock=time.monotonic) -> Iterator[dict]` yielding, in order: `{"type":"step","label":"Pregunta revisada","status":"running"}` … `{"type":"step",…,"status":"done","ms":int}` per step, then exactly one terminal `{"type":"answer","text":str,"session_id":str,"guard":dict}` or `{"type":"error","message":str}`. Guards (mask is done by the caller; this runs Model Armor → topic → agent → leak/links/PII/Model Armor out) exactly as today's `/chat`; a guard block yields `answer` with the `REPLY[...]` text.
- Step mapping from Agent Runtime events: `Pregunta revisada` = the input guards; `Buscando en los manuales` = from `stream_query` start until its first event (the pre-retrieval search) and again for each `function_call` named `buscar_catalogo_hibrido` until its `function_response`; `Consultando precio y stock` = `function_call` `consultar_precio_stock` until its response; `Redactando la respuesta` = from the last tool response (or first event if none) to the final text.

- [ ] **Step 1: Failing tests** with a `FakeRemote` replaying recorded event lists: price question → labels in order `[Pregunta revisada, Buscando en los manuales, Consultando precio y stock, Redactando la respuesta]`, each `running` then `done` with `ms` ≥ 0 (fake clock); Model Armor hit → no agent call, terminal `answer` = `REPLY["blocked"]`; runtime `error_code` and no text → terminal `error`; `/chat` JSON response for a normal question is byte-for-byte the same shape as before (`session_id`, `answer`, `seconds`, `guard`).
- [ ] **Step 2: Run** `uv run pytest api/tests/test_gcp_agent.py -v` → FAIL.
- [ ] **Step 3: Implement** by moving today's `/chat` body into `gcp_events` and rewriting `/chat` to consume it and return the old JSON.
- [ ] **Step 4: Run** this file and Task 1-4 tests → PASS.
- [ ] **Step 5: Commit** `refactor(sg-api): Google Cloud agent as a step stream`.

### Task 6: Parallel blind stream (`stream.py`)

**Files:**
- Create: `api/stream.py`, `api/tests/test_stream.py`

**Interfaces:**
- Consumes: `gcp_events` (Task 5), `ask_n8n` (Task 4).
- Produces: `n8n_events(ask: Callable[[], str], clock, sleep) -> Iterator[dict]` (simulated steps: `Pregunta revisada` done at 1.0 s, `Buscando en los manuales` done at 3.0 s, then `Redactando la respuesta` running until `ask()` returns; terminal `answer` or `error`); `merge_blind(slots: dict[Literal["A","B"], Iterator[dict]]) -> Iterator[dict]` running both iterators in threads and yielding events tagged with `slot`, dropping `ms` from steps, converting terminals to `answer`/`error` with `total_ms`; `sse(event: str, data: dict) -> str` (`"event: {event}\ndata: {json}\n\n"`, UTF-8, `ensure_ascii=False`).

- [ ] **Step 1: Failing tests:** slow slot does not delay the fast slot's `answer` (fake iterators with events gated by `threading.Event`); a slot raising mid-way → `error` with `"Este agente no ha podido responder ahora."`; no event dict contains `ms` or the strings `gcp`/`n8n`; `sse()` round-trips Spanish text; `n8n_events` with fake clock emits the three labels in order and `ask` failure → `error`.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_stream.py -v` → FAIL.
- [ ] **Step 3: Implement** with a `queue.Queue` and one thread per slot; a sentinel per slot marks completion.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): parallel blind event stream`.

### Task 7: `POST /compare`

**Files:**
- Modify: `api/main.py`
- Create: `api/tests/test_compare.py`

**Interfaces:**
- Consumes: `CompareStore` (Task 3, injected via a `get_store()` dependency; tests override with `MemoryStore`), `merge_blind`, `n8n_events`, `gcp_events`, `rate_limit`, `guards.mask_pii`.
- Produces: the `/compare` SSE contract. New conversation: `mapping_a = random.choice(["gcp","n8n"])` (injectable `rng`); the GCP session id from the first `answer` is saved with `set_gcp_session` and reused for follow-ups; the n8n `conversationId` is the conversation id.

- [ ] **Step 1: Failing tests** (fake agents, `MemoryStore`, fixed `rng`): first event is `conversation`; slot B receives the agent that `mapping_a` doesn't name; body of the whole stream contains none of `gcp`, `n8n`, `Google`; `rate_limit` called once; follow-up with the same `conversation_id` reuses the stored GCP session; unknown/other user's `conversation_id` → 404; revealed conversation → 409 `"conversation closed"` and no agent called; message with an email reaches both fake agents masked (`<EMAIL>`); a failed slot → `done.votable == false`; `add_comparison` row has both `total_ms`.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_compare.py -v` → FAIL.
- [ ] **Step 3: Implement** with `StreamingResponse(media_type="text/event-stream")`, header `Cache-Control: no-cache`; the generator writes the comparison row after both terminals and then emits `done`.
- [ ] **Step 4: Run** all `api/tests` → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): /compare (blind, both agents, streamed)`.

### Task 8: Vote and reveal

**Files:**
- Modify: `api/main.py`
- Create: `api/tests/test_vote_reveal.py`

**Interfaces:**
- Consumes: `CompareStore.vote`, `CompareStore.reveal`.
- Produces: `POST /compare/{comparison_id}/vote`, `POST /conversations/{conversation_id}/reveal` per the contract; both require `user` and `demo`.

- [ ] **Step 1: Failing tests:** vote `"A"` → `{"ok": true}` and the response has no mapping; second vote → 409; another user's id → 404; invalid vote value → 422; vote on a non-votable comparison → 409; reveal returns `mapping` with both `A` and `B` set and comparisons with totals and votes; after reveal, vote → 409 and `/compare` on it → 409.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_vote_reveal.py -v` → FAIL.
- [ ] **Step 3: Implement** mapping store results to 200/404/409.
- [ ] **Step 4: Run** all `api/tests` → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): blind votes and end-of-conversation reveal`.

### Task 9: `POST /chat/stream` (single agent, steps with times)

**Files:**
- Modify: `api/main.py`
- Create: `api/tests/test_chat_stream.py`

**Interfaces:**
- Consumes: `gcp_events`, `rate_limit`, `guards.mask_pii`, `sse`.
- Produces: the `/chat/stream` contract (any role; demo not required).

- [ ] **Step 1: Failing tests:** `done` steps carry `ms`; terminal `answer` has `total_ms` and `session_id`; 401 without token; `rate_limit` called once; message masked.
- [ ] **Step 2: Run** `uv run pytest api/tests/test_chat_stream.py -v` → FAIL.
- [ ] **Step 3: Implement** with the same session reuse rules as `/chat` (role change → new session).
- [ ] **Step 4: Run** all `api/tests` → PASS.
- [ ] **Step 5: Commit** `feat(sg-api): /chat/stream with per-step times`.

### Task 10: Demo accounts in `infra/users.py`

**Files:**
- Modify: `infra/users.py`
- Create: `infra/tests/test_users_claims.py`

**Interfaces:**
- Produces: `claims_for(role: str, demo: bool) -> dict` (`{}` for `none`; `{"role": r}` or `{"role": r, "demo": True}`); CLI `add <email> <role> [--demo]`, `demo <email> on|off`; `test-users` also creates `test-demo@storegear-gcp.test` (staff + demo) and writes `STOREGEAR_TEST_DEMO_EMAIL/PASSWORD` to `agent/storegear/.env`.

- [ ] **Step 1: Failing tests** for `claims_for` (4 combinations; `demo` with role `none` → `{}`).
- [ ] **Step 2: Run** `uv run pytest infra/tests/test_users_claims.py -v` → FAIL.
- [ ] **Step 3: Implement** and route `set_role`/`add` through `claims_for` (custom attributes JSON).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(users): demo flag for jury accounts`.

### Task 11: Configure, deploy, live check (needs Alexander)

**Files:**
- Modify: `infra/runbook.md`, `api/cloudbuild.yaml` (no change expected), `docs/adr/017-web-demo-api.md` (new ADR: single door for both agents, blind comparison, votes)
- Create: `eval/compare_tests.py` (live: demo account → `/compare` → both answers → vote → reveal; non-demo → 403)

- [ ] **Step 1 (Alexander, Console/n8n UI):** create secret `n8n-jwt-secret` (≥ 32 random bytes, generated by Alexander, never pasted in chat); put the same value in n8n credential "JWT Auth account 2"; grant `sg-api` Secret Manager Secret Accessor **on that secret only**.
- [ ] **Step 2:** `uv run python infra/sql/apply.py infra/sql/009_web_demo.sql` → all statements `ok`.
- [ ] **Step 3:** `uv run pytest api/tests infra/tests -v` → all PASS.
- [ ] **Step 4 (Alexander):** build `sg-api:v5` and deploy with `--set-secrets STOREGEAR_N8N_JWT_SECRET=n8n-jwt-secret:latest` and `--update-env-vars STOREGEAR_ALLOWED_ORIGINS=<Firebase Hosting origins>`.
- [ ] **Step 5:** `uv run python infra/users.py test-users` (adds the demo account) and `uv run --env-file agent/storegear/.env python eval/compare_tests.py` → the n8n slot answers; the Google slot errors with the fixed message **while Agent Platform is restricted**, answers once it's restored. Regression: `auth_tests`, `session_tests` pass (guardrail tests only after access returns; they reach Gemini).
- [ ] **Step 6:** add to `infra/runbook.md` the vote retention step from the spec: once the SMO-29 report is written, `DELETE FROM compare_votes; DELETE FROM compare_conversations;` (export the summary first).
- [ ] **Step 7: Commit** `chore(sg-api): v5 deploy notes, ADR-017, live compare test`.
