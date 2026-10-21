"""SMO-24 · Session tests against the deployed sg-api (ADR-016).

    uv run --env-file agent/storegear/.env python eval/session_tests.py

 1  follow-up in the same session understands the earlier product
 2  GET /sessions lists the new session for its owner
 3  GET /sessions/{id} returns the conversation, fast (no model call)
 4  another user: GET, DELETE and /chat with that session id -> 404
 5  the session expires ~30 days after creation (checked on the platform)
 6  DELETE by the owner -> gone (404 afterwards)
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1]
API = os.environ["STOREGEAR_API_URL"].rstrip("/")
KEY = os.environ["STOREGEAR_IDP_API_KEY"]


def token(kind: str) -> str:
    r = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={KEY}", timeout=30,
                      json={"email": os.environ[f"STOREGEAR_TEST_{kind}_EMAIL"], "password": os.environ[f"STOREGEAR_TEST_{kind}_PASSWORD"],
                            "returnSecureToken": True})
    r.raise_for_status()
    return r.json()["idToken"]


def call(method: str, path: str, tok: str, body: dict | None = None) -> requests.Response:
    return requests.request(method, f"{API}{path}", json=body, headers={"Authorization": f"Bearer {tok}"}, timeout=180)


def expiry_days(session_id: str) -> float:
    engine = json.loads((ROOT / "infra" / "agent_runtime.json").read_text())["resource_name"]
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    x = AuthorizedSession(creds).get(f"https://aiplatform.eu.rep.googleapis.com/v1beta1/{engine}/sessions/{session_id}", timeout=30).json()
    t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return (t(x["expireTime"]) - t(x["createTime"])).total_seconds() / 86400


def main() -> None:
    staff, manager = token("STAFF"), token("MANAGER")
    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name:<42} {detail}")

    r1 = call("POST", "/chat", staff, {"message": "¿Cuánto cuesta el Polar Ignite 2?"}).json()
    sid = r1["session_id"]
    r2 = call("POST", "/chat", staff, {"message": "¿Y hay stock?", "session_id": sid}).json()
    a = r2.get("answer", "")
    check("1 follow-up keeps the context", r2.get("session_id") == sid and ("stock" in a.lower() or "unidad" in a.lower()) and "ignite" in a.lower(), repr(a[:110]))
    ids = [x["session_id"] for x in call("GET", "/sessions", staff).json().get("sessions", [])]
    check("2 owner lists the session", sid in ids, f"{len(ids)} sessions")
    t0 = time.time()
    h = call("GET", f"/sessions/{sid}", staff)
    took = time.time() - t0
    msgs = h.json().get("messages", []) if h.ok else []
    check("3 history without the model", h.ok and len(msgs) >= 4 and took < 3, f"{len(msgs)} messages in {took:.2f}s")
    g, d = call("GET", f"/sessions/{sid}", manager), call("DELETE", f"/sessions/{sid}", manager)
    c = call("POST", "/chat", manager, {"message": "¿Y el precio?", "session_id": sid})
    check("4 another user gets 404", (g.status_code, d.status_code, c.status_code) == (404, 404, 404), f"GET {g.status_code} · DELETE {d.status_code} · chat {c.status_code}")
    days = expiry_days(sid)
    check("5 expires ~30 days after creation", 29.9 < days < 30.1, f"{days:.2f} days")
    dd = call("DELETE", f"/sessions/{sid}", staff)
    after = call("GET", f"/sessions/{sid}", staff)
    check("6 owner deletes it", dd.ok and after.status_code == 404, f"DELETE {dd.status_code} · then GET {after.status_code}")
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
