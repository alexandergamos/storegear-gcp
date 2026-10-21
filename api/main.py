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
import os
import random
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import google.auth
import google.auth.transport.requests
import vertexai
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud.sql.connector import Connector
from google.oauth2 import id_token
from pydantic import BaseModel, Field

import guards

warnings.filterwarnings("ignore")
PROJECT = os.getenv("STOREGEAR_PROJECT_ID", "storegear-prod-ag26")
AGENT = os.getenv("STOREGEAR_AGENT_RESOURCE", "projects/1066603052728/locations/eu/reasoningEngines/1557471414884237312")
AGENT_LOCATION = os.getenv("STOREGEAR_AGENT_LOCATION", "eu")
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
DB_USER = os.getenv("STOREGEAR_API_DB_USER", f"sg-api@{PROJECT}.iam")
SESSION_TTL = os.getenv("STOREGEAR_SESSION_TTL", f"{30 * 24 * 3600}s")   # 30 days, then the platform deletes it (ADR-016)
PER_MIN, PER_DAY = int(os.getenv("STOREGEAR_RATE_PER_MIN", "20")), int(os.getenv("STOREGEAR_RATE_PER_DAY", "300"))
ROLES = {"staff", "manager"}
POOL = ThreadPoolExecutor(8)
REPLY = {   # what the employee sees when a guardrail stops a request (ADR-015)
    "blocked": "Lo siento, no puedo ayudar con esa petición. Puedo responder sobre los relojes del catálogo, su precio y stock, y las políticas de la tienda.",
    "off_topic": "Solo puedo ayudarte con los relojes del catálogo (especificaciones, uso, precio y stock) y con las políticas de la tienda. ¿Qué necesitas saber?",
    "leak": "No puedo compartir detalles internos sobre cómo funciono. ¿En qué te ayudo con el catálogo?",
}

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
    return {"uid": claims["sub"], "role": claims["role"]}


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


@app.get("/health")   # not /healthz: Cloud Run's front end reserves paths ending in "z"
def health() -> dict:
    return {"ok": True}


@app.post("/chat")
def chat(body: Ask, who: dict = Depends(user)) -> dict:
    rate_limit(who["uid"])
    # INPUT (ADR-015): PII masked first, so nothing downstream (Model Armor, the model, the session, logs) sees it
    message, pii_in = guards.mask_pii(body.message)
    f_armor, f_topic = POOL.submit(guards.armor, message), POOL.submit(guards.on_topic, message)
    try:
        hits, topic_ok = f_armor.result(), f_topic.result()
    except Exception:  # noqa: BLE001  fail closed: an unchecked question never reaches the agent
        raise HTTPException(503, "guardrail unavailable") from None
    guard = {"pii_in": pii_in}
    if hits:
        return {"session_id": body.session_id, "answer": REPLY["blocked"], "guard": {**guard, "blocked": "input", "filters": hits}}
    if not topic_ok:
        return {"session_id": body.session_id, "answer": REPLY["off_topic"], "guard": {**guard, "blocked": "off_topic"}}
    r = remote()
    sid = body.session_id
    if sid:
        try:
            s = r.get_session(user_id=who["uid"], session_id=sid)   # only the owner's sessions are found
        except Exception:  # noqa: BLE001
            raise HTTPException(404, "session not found") from None
        if (s.get("state") or {}).get("user:role") != who["role"]:
            sid = None   # the role changed since this session started: never reuse it
    if not sid:
        sid = r.create_session(user_id=who["uid"], state={"user:role": who["role"]}, ttl=SESSION_TTL)["id"]
    t0, answer, error = time.time(), [], None
    for ev in r.stream_query(user_id=who["uid"], session_id=sid, message=message):
        if ev.get("error_code"):
            error = ev["error_code"]
        for p in (ev.get("content") or {}).get("parts", []) or []:
            if p.get("text") and not p.get("thought") and ev.get("author") != "user":
                answer.append(p["text"])
    if not answer:
        raise HTTPException(502, f"agent error: {error or 'empty answer'}")
    # OUTPUT: leaks of how we're built, links outside the brands, PII, and Model Armor's harm filters
    text = answer[-1]
    found_leak = guards.leak(text)
    if found_leak:
        return {"session_id": sid, "answer": REPLY["leak"], "seconds": round(time.time() - t0, 1), "guard": {**guard, "blocked": "leak", "leak": found_leak}}
    text, links = guards.strip_links(text)
    text, pii_out = guards.mask_pii(text)
    try:
        hits_out = guards.armor(text, response=True)
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "guardrail unavailable") from None
    if hits_out:
        return {"session_id": sid, "answer": REPLY["blocked"], "seconds": round(time.time() - t0, 1), "guard": {**guard, "blocked": "output", "filters": hits_out}}
    return {"session_id": sid, "answer": text, "seconds": round(time.time() - t0, 1),
            "guard": {**guard, "pii_out": pii_out, "links_removed": links}}


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
