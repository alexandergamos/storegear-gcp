"""SMO-18 · Injection gate: check every parent section before it can reach the catalog (ADR-010).

    uv run python ingestion/check_catalog.py            # check data/catalog_v2/parents.csv -> data/catalog_v2/injection_check.jsonl
    uv run python ingestion/check_catalog.py --apply    # + record flags in catalog_quarantine, remove them from the live catalog

Runs after chunk_manuals.py and before embed/load. A section is quarantined when the regex tripwire OR the Gemini
classifier flags it, or when the check fails (fail closed). Results are cached by text hash, so a re-run only checks
new or changed sections. load_catalog.py skips every quarantined section that isn't 'approved'.
"""
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import injection_check as ic

ROOT = Path(__file__).resolve().parents[1]
PARENTS = ROOT / "data" / "catalog_v2" / "parents.csv"
CACHE = ROOT / "data" / "catalog_v2" / "injection_check.jsonl"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gemini(p: dict) -> dict:
    """The paid, slow half: cached by text hash. Errors are never cached, so the next run retries them."""
    try:
        g = ic.gemini_check(p["parent_context"])
    except Exception as e:
        g = {"score": None, "flag": True, "why": f"ERROR {type(e).__name__}: {e}"[:200]}
    return {"parent_id": p["parent_id"], "sha": sha(p["parent_context"]), "score": g["score"], "flag": g["flag"], "why": g["why"]}


def verdict(p: dict, g: dict) -> dict:
    """Regex re-runs every time (free, and its patterns change); fail closed on a Gemini error."""
    r = ic.regex_check(p["parent_context"])
    detector = "error" if g["score"] is None else "+".join(n for n, x in (("regex", r), ("gemini", g)) if x["flag"])
    return {"flag": bool(detector), "detector": detector, "score": g["score"], "sha": g["sha"], "span": g["why"] or r["why"]}


def main(apply: bool) -> None:
    csv.field_size_limit(2**31 - 1)
    parents = list(csv.DictReader(open(PARENTS, encoding="utf-8", newline="")))
    cache = {}
    if CACHE.exists():
        for line in open(CACHE, encoding="utf-8"):
            c = json.loads(line)
            if c.get("score") is not None:   # first-run lines held the combined verdict: keep only Gemini's part
                cache[(c["parent_id"], c["sha"])] = {"parent_id": c["parent_id"], "sha": c["sha"], "score": c["score"],
                                                     "flag": c["score"] >= 0.5, "why": c.get("why", "")}
    todo = [p for p in parents if (p["parent_id"], sha(p["parent_context"])) not in cache]
    print(f"{len(parents)} sections · {len(parents) - len(todo)} cached · checking {len(todo)}")
    t0 = time.time()
    with ThreadPoolExecutor(6) as pool, open(CACHE, "a", encoding="utf-8") as out:
        for i, res in enumerate(pool.map(gemini, todo), 1):
            cache[(res["parent_id"], res["sha"])] = res
            out.write(json.dumps(res, ensure_ascii=False) + "\n")
            if i % 250 == 0:
                print(f"  {i}/{len(todo)} · {time.time() - t0:.0f}s", flush=True)
    results = [verdict(p, cache[(p["parent_id"], sha(p["parent_context"]))]) for p in parents]
    flagged = [(p, r) for p, r in zip(parents, results) if r["flag"]]
    by = {}
    for _, r in flagged:
        by[r["detector"]] = by.get(r["detector"], 0) + 1
    print(f"done in {time.time() - t0:.0f}s · flagged {len(flagged)} " + str(by or ""))
    for p, r in flagged:
        print(f"  {r['detector']:<13} {r['score'] if r['score'] is not None else '-':<5} {p['header_path'][-60:]!r}  span {r['span'][:90]!r}")
    if apply:
        record(flagged)


def record(flagged: list) -> None:
    from load_catalog import connect
    conn = connect()
    cur = conn.cursor()
    for p, r in flagged:
        cur.execute("""
            INSERT INTO catalog_quarantine (parent_id, file_id, header_path, parent_context, text_sha256, detector, score, span)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (parent_id) DO UPDATE SET
              file_id = EXCLUDED.file_id, header_path = EXCLUDED.header_path, parent_context = EXCLUDED.parent_context,
              detector = EXCLUDED.detector, score = EXCLUDED.score, span = EXCLUDED.span, checked_at = now(),
              text_sha256 = EXCLUDED.text_sha256,
              status = CASE WHEN catalog_quarantine.text_sha256 = EXCLUDED.text_sha256 THEN catalog_quarantine.status ELSE 'pending' END,
              reviewed_at = CASE WHEN catalog_quarantine.text_sha256 = EXCLUDED.text_sha256 THEN catalog_quarantine.reviewed_at END""",
                    (p["parent_id"], p["file_id"], p["header_path"], p["parent_context"], r["sha"], r["detector"], r["score"], r["span"]))
    cur.execute("SELECT parent_id FROM catalog_quarantine WHERE status <> 'approved'")
    blocked = [x[0] for x in cur.fetchall()]
    cur.execute("DELETE FROM catalog_chunks WHERE parent_id = ANY(%s)", (blocked,))
    n_chunks = cur.rowcount
    cur.execute("DELETE FROM catalog_parents WHERE parent_id = ANY(%s)", (blocked,))
    conn.commit()
    print(f"quarantine: {len(flagged)} recorded · {len(blocked)} blocked · removed from live catalog: {n_chunks} chunks, {cur.rowcount} sections")
    conn.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
