"""SMO-35 · Live checks of the web demo endpoints against the deployed sg-api (ADR-017).

    uv run --env-file agent/storegear/.env python eval/compare_tests.py

 1  GET /catalog/models is public and lists the staff manuals
 2  a staff account without the demo claim gets 403 on /compare
 3  a demo account gets one stream: conversation first, one terminal per slot, then done
 4  no agent name in the stream (gcp, n8n, Google)
 5  the n8n slot answers (known only after reveal); the Google slot answers once Agent Platform access is back
 6  vote once -> ok (or 409 if a slot failed); a second vote -> 409
 7  reveal -> mapping for A and B with the question's totals; after reveal, /compare on it -> 409
 8  /chat/stream: steps with times, then an answer (the fixed error passes only while /status says restricted)
"""
import json
import os
import sys

import requests

API = os.environ["STOREGEAR_API_URL"].rstrip("/")
KEY = os.environ["STOREGEAR_IDP_API_KEY"]
QUESTION = "¿Cuánto dura la batería del Polar Grit X2?"
FAILED = "Este agente no ha podido responder ahora."


def token(kind: str) -> str:
    r = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={KEY}", timeout=30,
                      json={"email": os.environ[f"STOREGEAR_TEST_{kind}_EMAIL"], "password": os.environ[f"STOREGEAR_TEST_{kind}_PASSWORD"],
                            "returnSecureToken": True})
    r.raise_for_status()
    return r.json()["idToken"]


def call(method: str, path: str, tok: str | None, body: dict | None = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return requests.request(method, f"{API}{path}", json=body, headers=headers, timeout=200)


def events(r: requests.Response) -> list[tuple[str, dict]]:
    out = []
    for block in r.content.decode("utf-8").strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def main() -> None:
    staff, demo = token("STAFF"), token("DEMO")
    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name:<44} {detail}")

    m = call("GET", "/catalog/models", None)
    models = m.json().get("models", []) if m.ok else []
    check("1 public model list", m.ok and len(models) >= 9, f"{len(models)} models")
    r = call("POST", "/compare", staff, {"message": QUESTION})
    check("2 no demo claim -> 403", r.status_code == 403, str(r.status_code))

    r = call("POST", "/compare", demo, {"message": QUESTION})
    ev = events(r) if r.ok else []
    terminals = {d["slot"]: (e, d) for e, d in ev if e in ("answer", "error")}
    shape = bool(ev) and ev[0][0] == "conversation" and ev[-1][0] == "done" and set(terminals) == {"A", "B"}
    check("3 one stream, one terminal per slot", shape, f"{r.status_code} · {len(ev)} events")
    body = r.content.decode("utf-8")
    check("4 no agent names on the wire", not any(w in body for w in ("gcp", "n8n", "Google")))
    if not shape:
        sys.exit(f"\n{sum(results)}/{len(results)} passed (stream unusable, stopping)")
    cid, done = ev[0][1]["conversation_id"], ev[-1][1]

    v1 = call("POST", f"/compare/{done['comparison_id']}/vote", demo, {"vote": "A"})
    v2 = call("POST", f"/compare/{done['comparison_id']}/vote", demo, {"vote": "B"})
    first_ok = v1.status_code == (200 if done["votable"] else 409)
    check("6 vote once, never twice", first_ok and v2.status_code == 409, f"votable {done['votable']} · {v1.status_code} · {v2.status_code}")

    rv = call("POST", f"/conversations/{cid}/reveal", demo)
    mapping = rv.json().get("mapping", {}) if rv.ok else {}
    by_agent = {mapping.get(slot): terminals[slot] for slot in ("A", "B")}
    n8n_e, n8n_d = by_agent.get("n8n", ("missing", {}))
    gcp_e, gcp_d = by_agent.get("gcp", ("missing", {}))
    check("5 n8n slot answers", n8n_e == "answer", f"{n8n_d.get('total_ms')} ms · {n8n_d.get('text', '')[:60]!r}")
    print(f"      Google Cloud slot: {gcp_e} ({gcp_d.get('total_ms')} ms) {gcp_d.get('text', gcp_d.get('message', ''))[:60]!r}")
    comps = rv.json().get("comparisons", []) if rv.ok else []
    after = call("POST", "/compare", demo, {"message": QUESTION, "conversation_id": cid})
    check("7 reveal, then the conversation is closed", sorted(mapping.values()) == ["gcp", "n8n"] and len(comps) == 1 and after.status_code == 409,
          f"mapping {mapping} · then {after.status_code}")

    s = call("POST", "/chat/stream", staff, {"message": QUESTION})
    sev = events(s) if s.ok else []
    timed = [d for e, d in sev if e == "step" and d.get("status") == "done"]
    end = sev[-1] if sev else ("none", {})
    # while restricted the topic check (Gemini) fails before any step is done: only then is the fixed error expected
    restricted = requests.get(f"{API}/status", timeout=30).json().get("gcp") == "restricted"
    ok = (end[0] == "answer" and bool(timed) and all(isinstance(d.get("ms"), int) for d in timed)) or \
         (restricted and end[0] == "error" and end[1].get("message") == FAILED)
    check("8 /chat/stream steps with times", ok, f"{[d['label'] for d in timed]} · {end[0]}")
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
