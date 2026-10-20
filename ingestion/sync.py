"""SMO-20 · Drive sync: one reconciliation pass (ADR-012). Called by the worker with --sync, before it drains the queue.

Compares DESIRED state (the PDFs in the two Drive folders) with ACTUAL state (the last queued version of each file and
what the catalog holds) and enqueues the difference:
- add / change / move: version key "md5:access_level" differs from the file's last queued version -> upsert
- delete: in the catalog but no longer in Drive -> delete (never the pseudo-manual polar-common)
- guard: an EMPTY listing never deletes anything (a Drive outage or a lost share must not wipe the catalog)
Every enqueue is INSERT ... ON CONFLICT DO NOTHING, so running the sync twice changes nothing.
"""
import os

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

from chunk_manuals import COMMON
from load_catalog import PROJECT

SA = f"sg-ingestion@{PROJECT}.iam.gserviceaccount.com"
FOLDERS = {  # folder id -> access level
    os.getenv("STOREGEAR_DRIVE_ROOT", "1fcYTK5j8ZUl3w8kQDJjXoMA-0uZONsC6"): "staff",            # "Shop Assitant"
    os.getenv("STOREGEAR_DRIVE_INTERNAL", "17_mV7pI6GM7gifvGL1OxnTeWJMxaJO0j"): "manager",       # "Internal (manager)"
}
DRIVE = "https://www.googleapis.com/drive/v3/files"
ALL_DRIVES = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
ENQUEUE = """INSERT INTO ingest_queue (file_id, file_name, access_level, action, content_hash, target)
VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (file_id, content_hash, action, target) DO NOTHING RETURNING id"""


def drive_session() -> AuthorizedSession:
    """Drive needs its own OAuth scope; the job's metadata token doesn't carry it, so sg-ingestion impersonates itself
    (Token Creator granted ON sg-ingestion only, ADR-002 addendum)."""
    base, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(impersonated_credentials.Credentials(
        source_credentials=base, target_principal=SA, target_scopes=["https://www.googleapis.com/auth/drive.readonly"]))


def list_drive(s: AuthorizedSession) -> dict[str, dict]:
    files = {}
    for folder, access in FOLDERS.items():
        token = None
        while True:
            r = s.get(DRIVE, params={**ALL_DRIVES, "pageSize": 1000, "pageToken": token or "",
                                     "q": f"'{folder}' in parents and trashed = false and mimeType = 'application/pdf'",
                                     "fields": "nextPageToken, files(id, name, md5Checksum)"}, timeout=60)
            r.raise_for_status()
            body = r.json()
            for f in body.get("files", []):
                files[f["id"]] = {"name": f["name"], "access": access, "key": f"{f['md5Checksum']}:{access}"}
            token = body.get("nextPageToken")
            if not token:
                break
    return files


def run(conn, target: str = "", rebuild: bool = False) -> dict:
    """One reconciliation pass for a target catalog ('' = live). rebuild=True enqueues every Drive file."""
    listing = list_drive(drive_session())
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ON (file_id) file_id, content_hash, action FROM ingest_queue WHERE target = %s "
                "ORDER BY file_id, created_at DESC", (target,))
    last = {fid: (h, a) for fid, h, a in cur.fetchall()}
    cur.execute(f"SELECT DISTINCT file_id, file_name FROM catalog_chunks{target} WHERE file_id <> %s", (COMMON[0],))
    in_catalog = dict(cur.fetchall())

    stats = {"listed": len(listing), "upserts": 0, "deletes": 0, "empty_listing": not listing}
    for fid, f in listing.items():
        if rebuild or last.get(fid) != (f["key"], "upsert"):
            cur.execute(ENQUEUE, (fid, f["name"], f["access"], "upsert", f["key"], target))
            stats["upserts"] += cur.fetchone() is not None
    if listing:   # the guard: never delete on an empty listing
        for fid in set(in_catalog) - set(listing):
            cur.execute(ENQUEUE, (fid, in_catalog[fid], "staff", "delete", (last.get(fid) or ("unknown",))[0], target))
            stats["deletes"] += cur.fetchone() is not None
    conn.commit()
    return stats
