"""SMO-22 · Admin script: shop users and their role (ADR-014). Run by Alexander, never by the app.

    uv run python infra/users.py add ana@tienda.es staff          # creates the user; prints nothing secret
    uv run python infra/users.py add jurado1@ejemplo.es staff --demo  # jury account: sees the blind comparison (ADR-017)
    uv run python infra/users.py demo jurado1@ejemplo.es off       # turns the comparison off, keeps the role
    uv run python infra/users.py jury jurado@storegear-gcp.test    # the jury's demo account; password to agent/storegear/.env
    uv run python infra/users.py jury iraitz@storegear-gcp.test iraitz   # one more juror: STOREGEAR_JURY_IRAITZ_* keys
    uv run python infra/users.py role ana@tienda.es manager        # changes the role (takes effect at next token refresh, <= 1 h)
    uv run python infra/users.py role ana@tienda.es none           # removes the role -> sg-api answers 403
    uv run python infra/users.py disable ana@tienda.es
    uv run python infra/users.py test-users                        # 4 test users (staff, manager, no role, staff+demo) for eval/

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


def claims_for(role: str, demo: bool) -> dict:
    """The custom claims sg-api trusts: role, and demo (only with a role)."""
    if role == "none":
        return {}
    return {"role": role, "demo": True} if demo else {"role": role}


def current_claims(s, email: str) -> tuple[str, str, bool] | None:
    """(uid, role or "none", demo) from Identity Platform, or None if there's no such user."""
    users = call(s, ":lookup", {"email": [email]}).get("users", [])
    if not users:
        return None
    attrs = json.loads(users[0].get("customAttributes") or "{}")
    return users[0]["localId"], attrs.get("role", "none"), attrs.get("demo") is True


def set_role(s, uid: str, role: str, demo: bool = False) -> None:
    call(s, ":update", {"localId": uid, "customAttributes": json.dumps(claims_for(role, demo))})


def add(s, email: str, role: str, password: str | None = None, demo: bool = False) -> tuple[str, str]:
    password = password or secrets.token_urlsafe(18)
    uid = uid_of(s, email)
    if uid:
        call(s, ":update", {"localId": uid, "password": password})
    else:
        uid = call(s, "", {"email": email, "password": password, "emailVerified": True})["localId"]
    set_role(s, uid, role, demo)
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
        demo = "--demo" in args[3:]
        uid, _ = add(s, args[1], args[2], demo=demo)
        print(f"{args[1]}: uid {uid}, role {args[2]}{' + demo' if demo else ''} (temporary password generated; reset it from the app)")
    elif cmd == "role":
        uid, _, demo = current_claims(s, args[1]) or sys.exit(f"{args[1]}: not found")
        set_role(s, uid, args[2], demo)
        print(f"{args[1]}: role -> {args[2]} (effective at the next token refresh, within 1 h)")
    elif cmd == "demo":
        if len(args) < 3 or args[2] not in ("on", "off"):
            sys.exit(__doc__)
        uid, role, _ = current_claims(s, args[1]) or sys.exit(f"{args[1]}: not found")
        set_role(s, uid, role, args[2] == "on")
        print(f"{args[1]}: demo {args[2]}, role {role} (effective at the next token refresh, within 1 h)")
    elif cmd == "disable":
        uid = uid_of(s, args[1]) or sys.exit(f"{args[1]}: not found")
        call(s, ":update", {"localId": uid, "disableUser": True})
        print(f"{args[1]}: disabled")
    elif cmd == "jury":
        # separate from test-demo: the test run regenerates test passwords, this one must stay as handed over
        # an optional name gives a juror keys of their own, so a second account never overwrites the first
        prefix = f"STOREGEAR_JURY_{args[2].upper()}" if len(args) > 2 else "STOREGEAR_JURY"
        _, pw = add(s, args[1], "staff", demo=True)
        write_env({f"{prefix}_EMAIL": args[1], f"{prefix}_PASSWORD": pw})
        print(f"{args[1]}: role staff + demo; credentials written to {ENV.relative_to(ENV.parents[2])} (git-ignored)")
    elif cmd == "test-users":
        values = {}
        for kind, role, demo in (("STAFF", "staff", False), ("MANAGER", "manager", False), ("NOROLE", "none", False),
                                 ("DEMO", "staff", True)):
            email = f"test-{kind.lower()}@storegear-gcp.test"
            _, pw = add(s, email, role, demo=demo)
            values[f"STOREGEAR_TEST_{kind}_EMAIL"] = email
            values[f"STOREGEAR_TEST_{kind}_PASSWORD"] = pw
            print(f"{email}: role {role}{' + demo' if demo else ''}")
        write_env(values)
        print(f"credentials written to {ENV.relative_to(ENV.parents[2])} (git-ignored)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
