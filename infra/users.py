"""SMO-22 · Admin script: shop users and their role (ADR-014). Run by Alexander, never by the app.

    uv run python infra/users.py add ana@tienda.es staff          # creates the user; prints nothing secret
    uv run python infra/users.py role ana@tienda.es manager        # changes the role (takes effect at next token refresh, <= 1 h)
    uv run python infra/users.py role ana@tienda.es none           # removes the role -> sg-api answers 403
    uv run python infra/users.py disable ana@tienda.es
    uv run python infra/users.py test-users                        # 3 test users (staff, manager, no role) for eval/auth_tests.py

Passwords are generated here and written to agent/storegear/.env (git-ignored), never printed. Real staff reset
their own password from the sign-in screen of the future app. Sign-up is disabled in Identity Platform, so this
script is the only way an account or a role comes into existence.
"""
import json
import re
import secrets
import sys
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT = "storegear-prod-ag26"
BASE = f"https://identitytoolkit.googleapis.com/v1/projects/{PROJECT}/accounts"
ENV = Path(__file__).resolve().parents[1] / "agent" / "storegear" / ".env"


def session() -> AuthorizedSession:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    s = AuthorizedSession(creds)
    s.headers["x-goog-user-project"] = PROJECT
    return s


def call(s, path: str, body: dict) -> dict:
    r = s.post(BASE + path, json=body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"{path or 'create'}: {r.status_code} {r.json().get('error', {}).get('message', r.text)[:200]}")
    return r.json()


def uid_of(s, email: str) -> str | None:
    users = call(s, ":lookup", {"email": [email]}).get("users", [])
    return users[0]["localId"] if users else None


def set_role(s, uid: str, role: str) -> None:
    attrs = {} if role == "none" else {"role": role}
    call(s, ":update", {"localId": uid, "customAttributes": json.dumps(attrs)})


def add(s, email: str, role: str, password: str | None = None) -> tuple[str, str]:
    password = password or secrets.token_urlsafe(18)
    uid = uid_of(s, email)
    if uid:
        call(s, ":update", {"localId": uid, "password": password})
    else:
        uid = call(s, "", {"email": email, "password": password, "emailVerified": True})["localId"]
    set_role(s, uid, role)
    return uid, password


def write_env(values: dict[str, str]) -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    for k, v in values.items():
        line = f"{k}={v}"
        text = re.sub(rf"^{k}=.*$", line, text, flags=re.M) if re.search(rf"^{k}=", text, flags=re.M) else text.rstrip("\n") + "\n" + line + "\n"
    ENV.write_text(text, encoding="utf-8")


def main(args: list[str]) -> None:
    s = session()
    cmd = args[0]
    if cmd == "add":
        uid, _ = add(s, args[1], args[2])
        print(f"{args[1]}: uid {uid}, role {args[2]} (temporary password generated; reset it from the app)")
    elif cmd == "role":
        uid = uid_of(s, args[1]) or sys.exit(f"{args[1]}: not found")
        set_role(s, uid, args[2])
        print(f"{args[1]}: role -> {args[2]} (effective at the next token refresh, within 1 h)")
    elif cmd == "disable":
        uid = uid_of(s, args[1]) or sys.exit(f"{args[1]}: not found")
        call(s, ":update", {"localId": uid, "disableUser": True})
        print(f"{args[1]}: disabled")
    elif cmd == "test-users":
        values = {}
        for kind, role in (("STAFF", "staff"), ("MANAGER", "manager"), ("NOROLE", "none")):
            email = f"test-{kind.lower()}@storegear-gcp.test"
            _, pw = add(s, email, role)
            values[f"STOREGEAR_TEST_{kind}_EMAIL"] = email
            values[f"STOREGEAR_TEST_{kind}_PASSWORD"] = pw
            print(f"{email}: role {role}")
        write_env(values)
        print(f"credentials written to {ENV.relative_to(ENV.parents[2])} (git-ignored)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
