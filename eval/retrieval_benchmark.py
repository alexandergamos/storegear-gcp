"""SMO-11 · Offline retrieval benchmark: which embedding model finds the right manual?

    uv run python eval/retrieval_benchmark.py gemini-embedding-001 gemini-embedding-2

Dense-only (vector search alone, no keyword part, no fusion), so it isolates the embedding model.
For each eval question that names a source manual: rank chunks by cosine similarity, collapse to parent
sections (best chunk per parent, as the real query does), and check the top-5 parents.
Metrics: manual@1 (right manual first), manual@5 (right manual among top 5), MRR.
The full hybrid query is benchmarked in SMO-12 against the n8n result (18/18).
"""
import csv
import json
import sys

import numpy as np

sys.path.insert(0, "ingestion")
from embed_export import embed_texts  # noqa: E402

csv.field_size_limit(2**31 - 1)
with open("data/catalog_chunks.csv", encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))
file_of = [r["file_name"] for r in rows]
parent_of = [r["parent_id"] for r in rows]

qs = [q for q in json.load(open("eval/dataset.json", encoding="utf-8")) if q["manual"] and q["qid"] not in (21, 22)]


def evaluate(model: str) -> None:
    docs = np.load(f"data/emb_{model}.npy")
    qv = embed_texts(model, [q["question"] for q in qs], "RETRIEVAL_QUERY", workers=4)
    hit1 = hit5 = 0
    rr = 0.0
    misses = []
    for q, v in zip(qs, qv):
        targets = [m.strip() for m in q["manual"].split(";")]
        order = np.argsort(-(docs @ v))
        parents, files = [], []
        for i in order:
            if parent_of[i] not in parents:
                parents.append(parent_of[i])
                files.append(file_of[i])
            if len(parents) == 5:
                break
        ok1 = files[0] in targets
        ok5 = all(t in files for t in targets)  # comparisons need every manual in the top 5
        hit1 += ok1
        hit5 += ok5
        rank = next((k + 1 for k, f in enumerate(files) if f in targets), None)
        rr += 1 / rank if rank else 0
        if not (ok1 and ok5):
            misses.append(f"Q{q['qid']} top: {files[:3]}")
    n = len(qs)
    print(f"{model:22} manual@1 {hit1}/{n}  manual@5 {hit5}/{n}  MRR {rr / n:.3f}")
    for m in misses:
        print("   miss", m)


if __name__ == "__main__":
    for model in sys.argv[1:]:
        evaluate(model)
