"""SMO-22 · Authentication and authorisation tests against sg-api (ADR-014).

    uv run --env-file agent/storegear/.env python eval/auth_tests.py      # needs STOREGEAR_API_URL + test users

 1  no token                         -> 401
 2  garbage token                    -> 401
 3  valid token, no role claim       -> 403
 4  staff asks for supplier cost     -> 200, answer WITHOUT the internal figures (268 €, 33 %)
 5  manager asks the same            -> 200, answer WITH them
 6  role in the request body ignored -> staff sending {"role": "manager"} still gets no internal figures
 7  day quota exhausted              -> 429 (counter pre-filled as the database admin, then cleaned up)
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = os.environ["STOREGEAR_API_URL"].rstrip("/")
KEY = os.environ["STOREGEAR_IDP_API_KEY"]
QUESTION = "¿Cuál es el coste de proveedor y el margen bruto del Garmin Instinct 3 AMOLED?"
INTERNAL = ["268", "33 %", "33%"]
PER_DAY = int(os.getenv("STOREGEAR_RATE_PER_DAY", "300"))


def sign_in(kind: str) -> tuple[str, str]:
    r = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={KEY}", timeout=30,
                      json={"email": os.environ[f"STOREGEAR_TEST_{kind}_EMAIL"], "password": os.environ[f"STOREGEAR_TEST_{kind}_PASSWORD"],
                            "returnSecureToken": True})
    r.raise_for_status()
    return r.json()["idToken"], r.json()["localId"]


def chat(token: str | None, body: dict | None = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(f"{API}/chat", json=body or {"message": QUESTION}, headers=headers, timeout=180)


def admin_sql(sql: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
    subprocess.run([sys.executable, str(ROOT / "infra" / "sql" / "apply.py"), f.name], check=True, capture_output=True)
    os.unlink(f.name)


def main() -> None:
    staff, staff_uid = sign_in("STAFF")
    manager, _ = sign_in("MANAGER")
    norole, _ = sign_in("NOROLE")
    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    r = chat(None);                       check("1 no token -> 401", r.status_code == 401, str(r.status_code))
    r = chat("not-a-token");              check("2 garbage token -> 401", r.status_code == 401, str(r.status_code))
    r = chat(norole);                     check("3 no role claim -> 403", r.status_code == 403, str(r.status_code))
    r = chat(staff)
    a = r.json().get("answer", "") if r.ok else ""
    check("4 staff: no internal figures", r.ok and not any(m in a for m in INTERNAL), f"{r.status_code} · {a[:120]!r}")
    r = chat(manager)
    a = r.json().get("answer", "") if r.ok else ""
    check("5 manager: internal figures", r.ok and "268" in a, f"{r.status_code} · {a[:120]!r}")
    r = chat(staff, {"message": QUESTION, "role": "manager"})
    a = r.json().get("answer", "") if r.ok else ""
    check("6 role in body ignored", r.ok and not any(m in a for m in INTERNAL), f"{r.status_code} · {a[:120]!r}")
    admin_sql(f"INSERT INTO api_rate VALUES ('{staff_uid}', 'day', date_trunc('day', now()), {PER_DAY}) "
              f"ON CONFLICT (uid, kind, window_start) DO UPDATE SET count = {PER_DAY};")
    try:
        r = chat(staff);                  check("7 day quota -> 429", r.status_code == 429, str(r.status_code))
    finally:
        admin_sql(f"DELETE FROM api_rate WHERE uid = '{staff_uid}';")
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
