"""SMO-19 · Put manuals on the ingestion queue by hand (the Drive sync, SMO-20, will do this on a schedule).

    uv run python ingestion/enqueue.py "Ignite 2"            # local PDFs whose name contains the text
    uv run python ingestion/enqueue.py "Ignite 2" --delete   # remove that manual from the catalog

content_hash is the md5 of the bytes, which is exactly Drive's md5Checksum, so a later sync of the same file is a
no-op (ON CONFLICT DO NOTHING): enqueuing twice is safe.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_catalog import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PDFS = ROOT / "data" / "pdf" / "full"


def main(match: str, delete: bool) -> None:
    ids = {}
    for line in (PDFS / "file_ids.tsv").read_text(encoding="utf-8-sig").splitlines():
        fid, name = line.split("\t")
        ids[name.strip()] = fid.strip()
    conn = connect()
    cur = conn.cursor()
    for name, fid in sorted(ids.items()):
        if match.lower() not in name.lower():
            continue
        h = hashlib.md5((PDFS / name).read_bytes()).hexdigest()   # a delete carries the hash of the version it removes
        access = "manager" if "Interno" in name else "staff"
        cur.execute("INSERT INTO ingest_queue (file_id, file_name, access_level, action, content_hash) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (file_id, content_hash, action) DO NOTHING RETURNING id",
                    (fid, name, access, "delete" if delete else "upsert", h))
        row = cur.fetchone()
        print(f"{name}: " + (f"queued as job {row[0]}" if row else "already queued with this content (no-op)"))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1], "--delete" in sys.argv)
