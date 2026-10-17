"""SMO-12 · Retrieval benchmark of the full hybrid search (the agent's real tool) vs the n8n result.

    $env:STOREGEAR_IMPERSONATE_SA="sg-agent@storegear-prod-ag26.iam.gserviceaccount.com"   # test AS the agent
    uv run python eval/hybrid_benchmark.py

n8n reference (2026-10-08, 18 queries): right manual in top 5 18/18; right manual first 18/18; search median 1.33 s.
Here: the 17 eval questions with a known source manual (Q1-Q17; Q21/Q22 are duplicates) plus a manager-only check.
"""
import json
import statistics
import sys
import time

sys.path.insert(0, "agent")
from storegear.tools.search import hybrid_search  # noqa: E402

qs = [q for q in json.load(open("eval/dataset.json", encoding="utf-8")) if q["manual"] and q["qid"] not in (21, 22)]

hybrid_search("calentamiento")  # warm-up: opens the pooled connection, so timings measure search only

hit1 = hit5 = 0
times = []
for q in qs:
    targets = [m.strip() for m in q["manual"].split(";")]
    t = time.time()
    rows = hybrid_search(q["question"])
    times.append(time.time() - t)
    files = [r["file_name"] for r in rows]
    ok1, ok5 = files[0] in targets, all(m in files for m in targets)
    hit1 += ok1
    hit5 += ok5
    flag = "" if ok1 and ok5 else "   <-- " + ", ".join(files[:3])
    print(f"Q{q['qid']:<3} {'1st' if ok1 else '---'} {'top5' if ok5 else '----'} {times[-1]:.2f}s  {rows[0]['sources']:<22}{flag}")

n = len(qs)
print(f"\nmanual@1 {hit1}/{n} · manual@5 {hit5}/{n} · search median {statistics.median(times):.2f}s (n8n: 18/18, 18/18, 1.33s)")

# Access control: the internal manager manual must never reach staff
internal = "StoreGear_Interno_Encargados.pdf"
q = "procedimiento interno para encargados de tienda"
staff = [r["file_name"] for r in hybrid_search(q, role="staff")]
mgr = [r["file_name"] for r in hybrid_search(q, role="manager")]
print(f"role filter: staff sees internal manual: {internal in staff} (must be False) · manager sees it: {internal in mgr}")
