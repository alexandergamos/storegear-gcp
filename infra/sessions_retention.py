"""SMO-24 · Retention audit for Agent Platform Sessions (ADR-016). The TTL is the mechanism; this is the proof.

    uv run python infra/sessions_retention.py            # report + enforce
    uv run python infra/sessions_retention.py --dry-run  # report only

For every session of the deployed agent: older than MAX_DAYS -> deleted; expiring later than create + MAX_DAYS
(e.g. the 365-day default) -> expiry shortened to create + MAX_DAYS. Prints counts per user id prefix, never content.
"""
import collections
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

MAX_DAYS = 30
ROOT = Path(__file__).resolve().parents[1]
ENGINE = json.loads((ROOT / "infra" / "agent_runtime.json").read_text())["resource_name"]
HOST = "https://aiplatform.eu.rep.googleapis.com/v1beta1"


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def send(fn, *args, **kwargs):
    """The Sessions API rate-limits bursts (429): pace the writes and back off."""
    for attempt in range(6):
        r = fn(*args, **kwargs)
        if r.status_code != 429:
            r.raise_for_status()
            time.sleep(0.4)
            return r
        time.sleep(2 ** attempt)
    r.raise_for_status()


def main(dry: bool) -> None:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    s = AuthorizedSession(creds)
    sessions, token = [], None
    while True:
        r = s.get(f"{HOST}/{ENGINE}/sessions", params={"pageSize": 100, "pageToken": token or ""}, timeout=60)
        r.raise_for_status()
        sessions += r.json().get("sessions", [])
        token = r.json().get("nextPageToken")
        if not token:
            break
    now, limit = datetime.now(timezone.utc), timedelta(days=MAX_DAYS)
    stats = collections.Counter()
    for x in sessions:
        created, expires = ts(x["createTime"]), ts(x["expireTime"])
        if now - created > limit:
            stats["deleted (older than 30 d)"] += 1
            if not dry:
                send(s.delete, f"{HOST}/{x['name']}", timeout=60)
        elif expires - created > limit + timedelta(minutes=5):
            stats["expiry shortened to 30 d"] += 1
            if not dry:
                new = (created + limit).isoformat().replace("+00:00", "Z")
                send(s.patch, f"{HOST}/{x['name']}", params={"updateMask": "expireTime"}, json={"expireTime": new}, timeout=60)
        else:
            stats["already within 30 d"] += 1
    users = collections.Counter(x.get("userId", "?")[:8] for x in sessions)
    print(f"{len(sessions)} sessions · {dict(stats)} · {'DRY RUN' if dry else 'enforced'}")
    print("by user (prefix):", dict(users.most_common(8)))


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
