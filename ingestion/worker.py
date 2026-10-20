"""SMO-19 · Ingestion queue worker (ADR-011). Drains ingest_queue one manual at a time, then exits.

    uv run python ingestion/worker.py                  # laptop (impersonates sg-ingestion for the database)
    uv run python ingestion/worker.py --sync           # reconcile with Drive first (ADR-012), then drain
    STOREGEAR_CATALOG_SUFFIX=_v3 ... --sync --rebuild  # full rebuild into the _v3 side tables
    STOREGEAR_LOCAL_PDFS=1 uv run python ingestion/worker.py   # read PDFs from data/pdf/full/ instead of Drive
    Cloud Run job sg-ingest-worker: same command, STOREGEAR_RUNNING_AS_SA=1

The queue rules:
- CLAIM with FOR UPDATE SKIP LOCKED: two workers can never take the same row; the claim counts as an attempt, so a
  worker that crashes mid-job still uses one up.
- SUPERSEDED: if a newer version of the same file is already queued, the older one is skipped.
- FAILURE: back to 'queued' with exponential backoff (2, 4 min); at MAX_ATTEMPTS -> 'dead' + an INGEST_DEAD log line
  (severity ERROR) that a log-based alert emails to Alexander.
- STALE CLAIMS: rows 'running' for more than STALE_MIN minutes (the worker died) go back to the queue at start-up.
"""
import json
import os
import socket
import sys
import traceback
from pathlib import Path

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

sys.path.insert(0, str(Path(__file__).parent))
from load_catalog import PROJECT, connect  # noqa: E402
import sync  # noqa: E402
from pipeline import delete_manual, fold_common, process_manual  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS, STALE_MIN = 3, 30
TARGET = os.getenv("STOREGEAR_CATALOG_SUFFIX", "")   # "" = live catalog, "_v3" = rebuild side tables
WORKER = os.getenv("CLOUD_RUN_EXECUTION", socket.gethostname())
SA = f"sg-ingestion@{PROJECT}.iam.gserviceaccount.com"

REAP = f"""
UPDATE ingest_queue SET status = CASE WHEN attempts >= {MAX_ATTEMPTS} THEN 'dead' ELSE 'queued' END,
       claimed_by = NULL, last_error = 'stale claim: worker stopped mid-job', updated_at = now()
WHERE status = 'running' AND claimed_at < now() - interval '{STALE_MIN} minutes'
RETURNING id, file_name, status"""
CLAIM = """
UPDATE ingest_queue SET status = 'running', attempts = attempts + 1, claimed_at = now(), claimed_by = %s, updated_at = now()
WHERE id = (SELECT id FROM ingest_queue WHERE status = 'queued' AND target = %s AND next_attempt_at <= now()
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, file_id, file_name, access_level, action, attempts, created_at"""


def log(severity: str, message: str, **fields) -> None:
    """One JSON line per event: Cloud Logging reads severity and fields from it."""
    print(json.dumps({"severity": severity, "message": message, "worker": WORKER, **fields}, default=str), flush=True)


def fetch_pdf(file_id: str, file_name: str) -> bytes:
    local = ROOT / "data" / "pdf" / "full" / file_name
    if os.getenv("STOREGEAR_LOCAL_PDFS") == "1" and local.exists():
        return local.read_bytes()
    # Drive needs its own OAuth scope; the job's metadata token doesn't carry it, so sg-ingestion impersonates itself
    # (same pattern as the agent's Sheets tool, ADR-008)
    base, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds = impersonated_credentials.Credentials(source_credentials=base, target_principal=SA,
                                                 target_scopes=["https://www.googleapis.com/auth/drive.readonly"])
    r = AuthorizedSession(creds).get(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                                     params={"alt": "media", "supportsAllDrives": "true"}, timeout=300)
    r.raise_for_status()
    return r.content


def run_job(conn, job: dict) -> None:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM ingest_queue WHERE file_id = %s AND target = %s AND status = 'queued' AND created_at > %s LIMIT 1",
                (job["file_id"], TARGET, job["created_at"]))
    if cur.fetchone():
        cur.execute("UPDATE ingest_queue SET status = 'superseded', updated_at = now() WHERE id = %s", (job["id"],))
        conn.commit()
        log("INFO", "INGEST_SUPERSEDED", job=job["id"], file=job["file_name"])
        return
    if job["action"] == "delete":
        stats = delete_manual(conn, job["file_id"], TARGET)
    else:
        stats = process_manual(conn, fetch_pdf(job["file_id"], job["file_name"]), job["file_id"], job["file_name"], job["access_level"], TARGET)
    cur.execute("UPDATE ingest_queue SET status = 'done', stats = %s::jsonb, last_error = NULL, updated_at = now() WHERE id = %s",
                (json.dumps(stats), job["id"]))
    conn.commit()
    log("INFO", "INGEST_DONE", job=job["id"], file=job["file_name"], **stats)


def fail(conn, job: dict, err: Exception) -> None:
    conn.rollback()   # drop the half-written manual: the old version stays live
    cur = conn.cursor()
    msg = f"{type(err).__name__}: {err}"[:1000]
    if job["attempts"] >= MAX_ATTEMPTS:
        cur.execute("UPDATE ingest_queue SET status = 'dead', last_error = %s, updated_at = now() WHERE id = %s", (msg, job["id"]))
        conn.commit()
        log("ERROR", "INGEST_DEAD", job=job["id"], file=job["file_name"], attempts=job["attempts"], error=msg)
    else:
        cur.execute("UPDATE ingest_queue SET status = 'queued', last_error = %s, updated_at = now(), "
                    "next_attempt_at = now() + interval '1 minute' * power(2, attempts) WHERE id = %s", (msg, job["id"]))
        conn.commit()
        log("WARNING", "INGEST_RETRY", job=job["id"], file=job["file_name"], attempts=job["attempts"], error=msg,
            trace=traceback.format_exc()[-1500:])


def main(max_jobs: int = 50, do_sync: bool = False, rebuild: bool = False) -> None:
    conn = connect()
    cur = conn.cursor()
    if do_sync:
        st = sync.run(conn, TARGET, rebuild)
        log("ERROR" if st["empty_listing"] else "INFO", "SYNC_EMPTY_LISTING" if st["empty_listing"] else "SYNC_DONE", target=TARGET, **st)
    cur.execute(REAP)
    for row in cur.fetchall():
        log("WARNING", "INGEST_REAPED", job=row[0], file=row[1], status=row[2])
    conn.commit()
    done = changed = 0
    while done < max_jobs:
        cur.execute(CLAIM, (WORKER, TARGET))
        row = cur.fetchone()
        conn.commit()   # the claim is durable before the long work starts
        if not row:
            break
        job = dict(zip(["id", "file_id", "file_name", "access_level", "action", "attempts", "created_at"], row))
        log("INFO", "INGEST_START", job=job["id"], file=job["file_name"], action=job["action"], attempt=job["attempts"])
        try:
            run_job(conn, job)
            changed += 1
        except Exception as e:  # noqa: BLE001  one bad manual must not stop the queue
            fail(conn, job, e)
        done += 1
    if changed:   # manuals changed: re-check the shared Polar brand sections across the whole catalog
        log("INFO", "FOLD_COMMON", target=TARGET, **fold_common(conn, TARGET))
    log("INFO", "INGEST_IDLE", processed=done, target=TARGET)
    conn.close()


if __name__ == "__main__":
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    main(int(nums[0]) if nums else 50, "--sync" in sys.argv, "--rebuild" in sys.argv)
