"""SMO-19 · One manual end to end (ADR-011), called by the queue worker.

    PDF bytes -> parse (Gemini + coverage + Document AI fallback, ADR-009) -> chunk (table-aware, SMO-17)
    -> injection gate (regex + Gemini, ADR-010) -> embed (gemini-embedding-2, ADR-005)
    -> REPLACE the manual's rows in one transaction.

Replace, not upsert: re-processing a file deletes its old parents/chunks and writes the new ones in the same
transaction, so running the same job twice gives the same catalog (idempotent), and sections that disappeared from
a new version of the manual don't linger. The agent sees either the old manual or the new one, never half.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import injection_check as ic
from check_catalog import sha
from chunk_manuals import COMMON, build_manual, norm_title
from embed_export import embed_texts
from load_catalog import UPSERT_CHUNKS, UPSERT_PARENTS
from parse_manuals import parse_pdf_bytes

EMBED_MODEL = "gemini-embedding-2"
BATCH = 200
QUARANTINE = """
INSERT INTO catalog_quarantine (parent_id, file_id, header_path, parent_context, text_sha256, detector, score, span)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (parent_id) DO UPDATE SET
  file_id = EXCLUDED.file_id, header_path = EXCLUDED.header_path, parent_context = EXCLUDED.parent_context,
  detector = EXCLUDED.detector, score = EXCLUDED.score, span = EXCLUDED.span, checked_at = now(),
  text_sha256 = EXCLUDED.text_sha256,
  status = CASE WHEN catalog_quarantine.text_sha256 = EXCLUDED.text_sha256 THEN catalog_quarantine.status ELSE 'pending' END,
  reviewed_at = CASE WHEN catalog_quarantine.text_sha256 = EXCLUDED.text_sha256 THEN catalog_quarantine.reviewed_at END"""


def check_section(p: dict) -> dict:
    """Regex + Gemini on one section. A Gemini error is retried here; if it still fails, the exception fails the whole
    job, which the queue retries later. Unchecked text is never loaded (fail closed)."""
    r = ic.regex_check(p["parent_context"])
    for attempt in range(3):
        try:
            g = ic.gemini_check(p["parent_context"])
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    detector = "+".join(n for n, x in (("regex", r), ("gemini", g)) if x["flag"])
    return {**p, "sha": sha(p["parent_context"]), "detector": detector, "score": g["score"], "span": g["why"] or r["why"]}


def process_manual(conn, data: bytes, file_id: str, file_name: str, access: str) -> dict:
    t0 = time.time()
    cur = conn.cursor()
    md, report = parse_pdf_bytes(data)
    cur.execute("SELECT header_path, parent_context FROM catalog_parents WHERE file_id = %s", (COMMON[0],))
    common = {norm_title(hp.split(" > ", 1)[-1]): body for hp, body in cur.fetchall()}
    parents, chunks, folded = build_manual(md, file_name, file_id, access, common)

    with ThreadPoolExecutor(6) as pool:
        checked = list(pool.map(check_section, parents))
    cur.execute("SELECT parent_id, text_sha256 FROM catalog_quarantine WHERE file_id = %s AND status = 'approved'", (file_id,))
    approved = set(cur.fetchall())
    flagged = [c for c in checked if c["detector"] and (c["parent_id"], c["sha"]) not in approved]
    blocked = {c["parent_id"] for c in flagged}
    parents = [p for p in parents if p["parent_id"] not in blocked]
    chunks = [c for c in chunks if c["parent_id"] not in blocked]

    vecs = embed_texts(EMBED_MODEL, [c["header_path"] + "\n" + c["chunk_text"] for c in chunks], "RETRIEVAL_DOCUMENT", workers=8) if chunks else []
    as_vec = lambda v: "[" + ",".join(f"{x:.7f}" for x in v) + "]"  # noqa: E731  pgvector text format

    # one transaction: the agent sees the old manual or the new one, never half of each
    cur.execute("DELETE FROM catalog_chunks WHERE file_id = %s", (file_id,))
    cur.execute("DELETE FROM catalog_parents WHERE file_id = %s", (file_id,))
    for c in flagged:
        cur.execute(QUARANTINE, (c["parent_id"], file_id, c["header_path"], c["parent_context"], c["sha"], c["detector"], c["score"], c["span"]))
    for i in range(0, len(parents), BATCH):
        b = parents[i:i + BATCH]
        cur.execute(UPSERT_PARENTS.replace("{S}", ""), ([p["parent_id"] for p in b], [p["file_id"] for p in b],
                                                         [p["header_path"] for p in b], [p["parent_context"] for p in b]))
    for i in range(0, len(chunks), BATCH):
        b, v = chunks[i:i + BATCH], vecs[i:i + BATCH]
        cur.execute(UPSERT_CHUNKS.replace("{S}", ""), (
            [c["child_id"] for c in b], [c["parent_id"] for c in b], [c["file_id"] for c in b], [c["file_name"] for c in b],
            [c["header_path"] for c in b], [c["chunk_text"] for c in b], [c["product_category"] for c in b],
            [c["access_level"] for c in b], [as_vec(x) for x in v]))
    conn.commit()

    covs = [r["coverage"] for r in report]
    return {"pages": sum(len(r["pages"]) for r in report), "coverage_min": min(covs), "docai_batches": sum(r["parser"] == "docai" for r in report),
            "sections": len(parents), "chunks": len(chunks), "folded_common": len(folded), "quarantined": len(flagged),
            "seconds": round(time.time() - t0)}


def delete_manual(conn, file_id: str) -> dict:
    """The file left Drive: remove it from the catalog (its quarantine rows go too)."""
    cur = conn.cursor()
    cur.execute("DELETE FROM catalog_chunks WHERE file_id = %s", (file_id,))
    n = cur.rowcount
    cur.execute("DELETE FROM catalog_parents WHERE file_id = %s", (file_id,))
    cur.execute("DELETE FROM catalog_quarantine WHERE file_id = %s", (file_id,))
    conn.commit()
    return {"deleted_chunks": n}
