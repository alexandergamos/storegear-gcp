"""SMO-22 · sg-api: the only door to the agent for people (ADR-014).

    POST /chat  {"message": "...", "session_id": optional}   Authorization: Bearer <Identity Platform ID token>
    GET  /healthz

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

import google.auth
import google.auth.transport.requests
import vertexai
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud.sql.connector import Connector
from google.oauth2 import id_token
from pydantic import BaseModel, Field

warnings.filterwarnings("ignore")
PROJECT = os.getenv("STOREGEAR_PROJECT_ID", "storegear-prod-ag26")
AGENT = os.getenv("STOREGEAR_AGENT_RESOURCE", "projects/1066603052728/locations/eu/reasoningEngines/1557471414884237312")
AGENT_LOCATION = os.getenv("STOREGEAR_AGENT_LOCATION", "eu")
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
DB_USER = os.getenv("STOREGEAR_API_DB_USER", f"sg-api@{PROJECT}.iam")
PER_MIN, PER_DAY = int(os.getenv("STOREGEAR_RATE_PER_MIN", "20")), int(os.getenv("STOREGEAR_RATE_PER_DAY", "300"))
ROLES = {"staff", "manager"}

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
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/sqlservice.login"])
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


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/chat")
def chat(body: Ask, who: dict = Depends(user)) -> dict:
    rate_limit(who["uid"])
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
        sid = r.create_session(user_id=who["uid"], state={"user:role": who["role"]})["id"]
    t0, answer, error = time.time(), [], None
    for ev in r.stream_query(user_id=who["uid"], session_id=sid, message=body.message):
        if ev.get("error_code"):
            error = ev["error_code"]
        for p in (ev.get("content") or {}).get("parts", []) or []:
            if p.get("text") and not p.get("thought") and ev.get("author") != "user":
                answer.append(p["text"])
    if not answer:
        raise HTTPException(502, f"agent error: {error or 'empty answer'}")
    return {"session_id": sid, "answer": answer[-1], "seconds": round(time.time() - t0, 1)}
