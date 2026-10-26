"""SMO-22 · sg-api: the only door to the agent for people (ADR-014).

    POST /chat  {"message": "...", "session_id": optional}   Authorization: Bearer <Identity Platform ID token>
    GET  /sessions · GET /sessions/{id} · DELETE /sessions/{id}   the caller's own history, no LLM call (ADR-016)
    GET  /health

1. Verify the ID token (Google public keys, issuer + audience = this project, expiry)         -> 401
2. role = custom claim "role" in {staff, manager}; set only by infra/users.py (admin)          -> 403
3. Per-user rate limit (uid): per minute and per day, counters in Cloud SQL                   -> 429
4. Call Agent Runtime AS sg-api: session user_id = uid, state user:role = role FROM THE TOKEN.
   The request body can't carry a role; a session created with another role is never reused.
"""
import hashlib
import json
import logging
import os
import random
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import google.auth
import google.auth.transport.requests
import vertexai
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.cloud.sql.connector import Connector
from google.oauth2 import id_token
from pydantic import BaseModel, Field

import agents
import catalog
import cost
import guards
import stream
from store import CompareStore, PgStore, other

warnings.filterwarnings("ignore")
PROJECT = os.getenv("STOREGEAR_PROJECT_ID", "storegear-prod-ag26")
AGENT = os.getenv("STOREGEAR_AGENT_RESOURCE", "projects/1066603052728/locations/eu/reasoningEngines/1557471414884237312")
AGENT_LOCATION = os.getenv("STOREGEAR_AGENT_LOCATION", "eu")
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
DB_USER = os.getenv("STOREGEAR_API_DB_USER", f"sg-api@{PROJECT}.iam")
# honest mode (2026-10-23): while Google restricts Agent Platform, the web demo talks to n8n alone, by name
GCP_STATUS = os.getenv("STOREGEAR_GCP_STATUS", "ok")   # "ok" | "restricted"
RELEASE = os.getenv("STOREGEAR_RELEASE", "dev")   # the commit the CI deployed (ADR-018); ties each answer to its code
MODEL = os.getenv("STOREGEAR_MODEL", "gemini-3.8-flash")
PER_MIN, PER_DAY = int(os.getenv("STOREGEAR_RATE_PER_MIN", "20")), int(os.getenv("STOREGEAR_RATE_PER_DAY", "300"))
ROLES = {"staff", "manager"}
POOL = ThreadPoolExecutor(8)
REPLY = agents.REPLY
log = logging.getLogger("sg-api")   # WARNING lines go to stderr as JSON; Cloud Logging reads them as structured entries

app = FastAPI(title="StoreGear API", docs_url=None, redoc_url=None, openapi_url=None)   # no public API map
app.add_middleware(CORSMiddleware, allow_origins=[o for o in os.getenv("STOREGEAR_ALLOWED_ORIGINS", "").split(",") if o],
                   allow_methods=["POST", "GET"], allow_headers=["Authorization", "Content-Type"])

_lock = threading.Lock()
_remote = None
_connector: Connector | None = None
_http = google.auth.transport.requests.Request()


def remote():
    global _remote
    with _lock:
        if _remote is None:
            _remote = vertexai.Client(project=PROJECT, location=AGENT_LOCATION).agent_engines.get(name=AGENT)
        return _remote


def db():
    global _connector
    with _lock:
        if _connector is None:
            # the connector needs cloud-platform too (it asks the Cloud SQL Admin API for connection settings)
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/sqlservice.login",
                                                   "https://www.googleapis.com/auth/cloud-platform"])
            _connector = Connector(credentials=creds)
    return _connector.connect(INSTANCE, "pg8000", user=DB_USER, db="storegear", enable_iam_auth=True)


def user(authorization: str = Header(default="")) -> dict:
    """401 unless a valid Identity Platform ID token; 403 unless it carries a known role."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        claims = id_token.verify_firebase_token(authorization[7:], _http, audience=PROJECT)
    except Exception:  # noqa: BLE001  expired, wrong signature, wrong project...: all the same to the caller
        raise HTTPException(401, "invalid token") from None
    if not claims or claims.get("role") not in ROLES:
        raise HTTPException(403, "no role assigned")
    # demo accounts (jury) see the blind comparison; only a literal JSON true counts
    return {"uid": claims["sub"], "role": claims["role"], "demo": claims.get("demo") is True}


def rate_limit(uid: str) -> None:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO api_rate (uid, kind, window_start, count) VALUES
                         (%s, 'min', date_trunc('minute', now()), 1), (%s, 'day', date_trunc('day', now()), 1)
                       ON CONFLICT (uid, kind, window_start) DO UPDATE SET count = api_rate.count + 1
                       RETURNING kind, count""", (uid, uid))
        counts = dict(cur.fetchall())
        if random.random() < 0.01:   # housekeeping: old windows are useless
            cur.execute("DELETE FROM api_rate WHERE window_start < now() - interval '2 days'")
        conn.commit()
    finally:
        conn.close()
    if counts["min"] > PER_MIN or counts["day"] > PER_DAY:
        raise HTTPException(429, "too many requests", headers={"Retry-After": "60"})


class Ask(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class CompareAsk(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


def demo_user(who: dict = Depends(user)) -> dict:
    if not who["demo"]:
        raise HTTPException(403, "demo only")
    return who


@app.get("/health")   # not /healthz: Cloud Run's front end reserves paths ending in "z"
def health() -> dict:
    return {"ok": True}


@app.post("/chat")
def chat(body: Ask, who: dict = Depends(user)) -> dict:
    rate_limit(who["uid"])
    # INPUT (ADR-015): PII masked first, so nothing downstream (Model Armor, the model, the session, logs) sees it
    message, pii_in = guards.mask_pii(body.message)
    end = None
    for end in watched("gcp", agents.gcp_events(remote, who["uid"], who["role"], message, body.session_id), who["uid"], None, who["role"]):
        pass
    if end["type"] == "error":
        raise HTTPException(end["status"], end["message"])
    out = {"session_id": end["session_id"], "answer": end["text"]}
    if "seconds" in end:
        out["seconds"] = end["seconds"]
    return {**out, "guard": {"pii_in": pii_in, **end["guard"]}}


MODELS_TTL = 600   # seconds; the catalog changes when a manual is ingested, a few times a week at most
_models_cache: tuple[float, list[str]] | None = None


def staff_file_names() -> list[str]:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT DISTINCT file_name FROM catalog_chunks
                       WHERE access_level = 'staff' AND file_id <> 'polar-common'""")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


@app.get("/catalog/models")   # public: the web demo's empty state lists the models before anyone signs in
def catalog_models() -> dict:
    global _models_cache
    if _models_cache is None or time.time() - _models_cache[0] > MODELS_TTL:
        _models_cache = (time.time(), catalog.list_models(staff_file_names))
    return {"models": _models_cache[1]}


def log_failure(agent: str, uid: str, conversation_id: str | None, reason: str) -> None:
    """Why an agent failed, for us; the client only ever sees the fixed text. Never the question or a token."""
    log.warning(json.dumps({"severity": "WARNING", "event": "AGENT_FAILED", "agent": agent, "uid": uid,
                            "conversation_id": conversation_id, "reason": reason[:300]}, ensure_ascii=False))


def uid_hash(uid: str) -> str:
    """Answers per user can be counted without the logs holding who they are."""
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def log_answer(agent: str, uid: str, role: str | None, conversation_id: str | None, steps: list[dict], total_ms: int, end: dict) -> None:
    """SMO-25/26 (ADR-019): what happened in one answer and what it cost. Never the question, the answer or the uid."""
    usage = end.get("usage")
    guard = (end.get("guard") or {}).get("blocked")
    price = cost.estimate(usage, end.get("topic_check", False)) if agent == "gcp" else None
    u = usage or {"tokens_in": 0, "tokens_cached": 0, "tokens_out": 0, "model_calls": 0}
    log.warning(json.dumps({
        "severity": "INFO", "event": "ANSWER", "agent": agent, "uid_hash": uid_hash(uid), "role": role,
        "conversation_id": conversation_id or end.get("session_id"), "guard": guard, "steps": steps, "total_ms": total_ms,
        "tokens_in": u["tokens_in"], "tokens_cached": u["tokens_cached"], "tokens_out": u["tokens_out"], "model_calls": u["model_calls"],
        "model": MODEL if agent == "gcp" else None, "release": RELEASE,
        "cost_eur": round(price["eur"], 7) if price else None, "cost_usd": round(price["usd"], 7) if price else None,
        **({"topic_skipped": end["topic_skipped"]} if end.get("topic_skipped") else {}),
    }, ensure_ascii=False))


def watched(agent: str, events, uid: str, conversation_id: str | None, role: str | None = None):
    """Passes an agent's events through, logging its error terminal or exception (then re-raising it),
    and one ANSWER line when it answers (ADR-019)."""
    t0, steps = time.monotonic(), []
    try:
        for e in events:
            if e["type"] == "error":
                log_failure(agent, uid, conversation_id, f"{e['message']} ({e['reason']})" if e.get("reason") else e["message"])
            elif e["type"] == "step" and e.get("status") == "done":
                steps.append({"label": e["label"], "ms": e.get("ms")})
            elif e["type"] == "answer":
                log_answer(agent, uid, role, conversation_id, steps, round((time.monotonic() - t0) * 1000), e)
            yield e
    except Exception as ex:
        log_failure(agent, uid, conversation_id, f"{type(ex).__name__}: {ex}")
        raise


@app.post("/chat/stream")
def chat_stream(body: Ask, who: dict = Depends(user)):
    """/chat for the web app: the same flow, streamed as progress steps with their real times (spec §6.2)."""
    rate_limit(who["uid"])
    message, _ = guards.mask_pii(body.message)

    def events():
        t0 = time.monotonic()
        end = None
        try:
            for e in watched("gcp", agents.gcp_events(remote, who["uid"], who["role"], message, body.session_id), who["uid"], None, who["role"]):
                if e["type"] == "step":
                    yield stream.sse("step", {k: e[k] for k in ("label", "status", "ms") if k in e})
                else:
                    end = e
        except Exception:  # noqa: BLE001  Agent Runtime unreachable or broken mid-stream: the client gets the fixed text
            end = None
        total_ms = round((time.monotonic() - t0) * 1000)
        if end and end["type"] == "answer":
            yield stream.sse("answer", {"text": end["text"], "total_ms": total_ms, "session_id": end["session_id"]})
        else:
            yield stream.sse("error", {"message": stream.FAILED, "total_ms": total_ms})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/status")   # public: the web app reads it to choose comparison or honest mode
def status() -> dict:
    return {"gcp": GCP_STATUS}


@app.post("/n8n/stream")
def n8n_stream(body: Ask, who: dict = Depends(user)):
    """Honest mode only: the n8n agent alone, by name. Its steps are simulated, so they carry no per-step time."""
    if GCP_STATUS != "restricted":
        raise HTTPException(404, "not available")
    rate_limit(who["uid"])
    message, _ = guards.mask_pii(body.message)
    conversation_id = (body.session_id or uuid.uuid4().hex)[:100]   # n8n keys its memory by this id

    def events():
        t0 = time.monotonic()
        end = None
        n8n = stream.n8n_events(lambda: agents.ask_n8n(message, who["uid"], conversation_id))
        for e in watched("n8n", n8n, who["uid"], conversation_id, who["role"]):
            if e["type"] == "step":
                yield stream.sse("step", {"label": e["label"], "status": e["status"]})
            else:
                end = e
        total_ms = round((time.monotonic() - t0) * 1000)
        if end and end["type"] == "answer":
            yield stream.sse("answer", {"text": end["text"], "total_ms": total_ms, "session_id": conversation_id})
        else:
            yield stream.sse("error", {"message": stream.FAILED, "total_ms": total_ms})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- blind comparison for the web demo (ADR-017)
RNG = random.SystemRandom()   # which agent is A, drawn once per conversation
_store: CompareStore | None = None


def get_store() -> CompareStore:
    global _store
    if _store is None:
        _store = PgStore(db)
    return _store


@app.post("/compare")
def compare(body: CompareAsk, who: dict = Depends(demo_user), store: CompareStore = Depends(get_store)):
    """Both agents at once, blind: slots A/B only; the mapping stays here until /conversations/{id}/reveal."""
    rate_limit(who["uid"])   # one compare = one request, although it asks two agents
    conv = None
    if body.conversation_id:
        conv = store.get_conversation(body.conversation_id, who["uid"])
        if not conv:
            raise HTTPException(404, "conversation not found")   # another user's id looks like a missing one
        if conv.revealed:
            raise HTTPException(409, "conversation closed")
    message, _ = guards.mask_pii(body.message)   # before EITHER agent sees it
    if not conv:
        conv = store.get_conversation(store.create_conversation(who["uid"], RNG.choice(["gcp", "n8n"])), who["uid"])

    # remote() runs inside the slot's thread, after the guards: if Agent Runtime is unreachable, only this slot fails
    gcp = agents.gcp_events(remote, who["uid"], who["role"], message, conv.gcp_session_id)
    n8n = stream.n8n_events(lambda: agents.ask_n8n(message, who["uid"], conv.id))
    by_agent = {"gcp": watched("gcp", gcp, who["uid"], conv.id, who["role"]), "n8n": watched("n8n", n8n, who["uid"], conv.id, who["role"])}
    gcp_slot = "A" if conv.mapping_a == "gcp" else "B"

    def events():
        yield stream.sse("conversation", {"conversation_id": conv.id})
        totals, failed = {"A": None, "B": None}, {"A": False, "B": False}
        for e in stream.merge_blind({"A": by_agent[conv.mapping_a], "B": by_agent[other(conv.mapping_a)]}):
            slot = e["slot"]
            if e["type"] == "step":
                yield stream.sse("step", {"slot": slot, "label": e["label"], "status": e["status"]})
                continue
            totals[slot] = e["total_ms"]
            if e["type"] == "answer":
                sid = e.get("session_id")
                if slot == gcp_slot and sid and sid != conv.gcp_session_id:
                    store.set_gcp_session(conv.id, sid)
                yield stream.sse("answer", {"slot": slot, "text": e["text"], "total_ms": e["total_ms"]})
            else:
                failed[slot] = True
                yield stream.sse("error", {"slot": slot, "message": e["message"], "total_ms": e["total_ms"]})
        k = store.add_comparison(conv.id, who["uid"], message, totals["A"], totals["B"], failed["A"], failed["B"])
        yield stream.sse("done", {"comparison_id": k, "votable": not (failed["A"] or failed["B"])})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class VoteBody(BaseModel):
    vote: Literal["A", "B", "tie"]


@app.post("/compare/{comparison_id}/vote")
def vote(comparison_id: str, body: VoteBody, who: dict = Depends(demo_user), store: CompareStore = Depends(get_store)) -> dict:
    result = store.vote(comparison_id, who["uid"], body.vote)
    if result == "not_found":
        raise HTTPException(404, "comparison not found")
    if result == "conflict":
        raise HTTPException(409, "already voted, not votable or conversation closed")
    return {"ok": True}


@app.post("/conversations/{conversation_id}/reveal")
def reveal(conversation_id: str, who: dict = Depends(demo_user), store: CompareStore = Depends(get_store)) -> dict:
    """Ends the conversation: from now on no questions or votes, and the client learns which agent was which."""
    out = store.reveal(conversation_id, who["uid"])
    if out is None:
        raise HTTPException(404, "conversation not found")
    return out


# ---------------------------------------------------------------- history (ADR-016): no model call, own sessions only
def _own(r, uid: str, sid: str) -> dict:
    try:   # ADK refuses a session whose user_id isn't the caller's: another user's id looks exactly like a missing one
        return r.get_session(user_id=uid, session_id=sid)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "session not found") from None


@app.get("/sessions")
def list_sessions(who: dict = Depends(user)) -> dict:
    res = remote().list_sessions(user_id=who["uid"])
    items = res.get("sessions", []) if isinstance(res, dict) else res
    return {"sessions": sorted(({"session_id": x.get("id"), "last_update": x.get("last_update_time") or x.get("lastUpdateTime")}
                                for x in items), key=lambda x: x["last_update"] or 0, reverse=True)}


@app.get("/sessions/{sid}")
def get_history(sid: str, who: dict = Depends(user)) -> dict:
    s = _own(remote(), who["uid"], sid)
    messages = []
    for ev in s.get("events", []):
        texts = [p["text"] for p in (ev.get("content") or {}).get("parts", []) or [] if p.get("text") and not p.get("thought")]
        if texts:
            messages.append({"role": "user" if ev.get("author") == "user" else "assistant", "text": texts[-1]})
    return {"session_id": sid, "messages": messages}


@app.delete("/sessions/{sid}")
def delete_history(sid: str, who: dict = Depends(user)) -> dict:
    r = remote()
    _own(r, who["uid"], sid)
    r.delete_session(user_id=who["uid"], session_id=sid)
    return {"deleted": sid}
