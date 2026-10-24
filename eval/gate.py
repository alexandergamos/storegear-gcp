"""SMO-28 · The release gate over the 22-question eval (ADR-018).

    uv run python eval/gate.py --retry-list first.json        # qids that failed on an availability error
    uv run python eval/gate.py first.json [rerun.json]        # exit 0 = PASS, 1 = FAIL

A single eval run is noisy (ADR-015: 4.64 then 5.00 with no change), so a question that failed because Google's
endpoint did (answer "ERROR ..." from run_eval.py) is run once more before scoring. A wrong answer is never retried.
Pass rule: every metric >= baseline - 0.1, and no availability error left.
"""
import json
import statistics
import sys

# the n8n baseline the Google Cloud build has to match (run_eval.py, 2026-10-11)
BASELINE = {"correctness": 5.00, "faithfulness": 4.95, "context_relevance": 5.00, "answer_relevance": 5.00}
TOLERANCE = 0.1
METRICS = tuple(BASELINE)


def is_unavailable(row: dict) -> bool:
    return str(row.get("answer", "")).startswith("ERROR ")


def retry_list(results: list[dict]) -> list[int]:
    return [r["qid"] for r in results if is_unavailable(r)]


def merge(first: list[dict], rerun: list[dict]) -> list[dict]:
    again = {r["qid"]: r for r in rerun}
    return [again.get(r["qid"], r) for r in first]


def summarize(results: list[dict]) -> dict:
    summary = {m: round(statistics.mean(r[m] for r in results if isinstance(r.get(m), int)), 2) for m in METRICS}
    return {**summary, "n": len(results)}


def verdict(summary: dict, baseline: dict = BASELINE, tolerance: float = TOLERANCE) -> tuple[bool, list[str]]:
    problems = [
        f"{m} {summary[m]:.2f} < {baseline[m] - tolerance:.2f} (baseline {baseline[m]:.2f} - {tolerance})"
        for m in METRICS
        if summary[m] < round(baseline[m] - tolerance, 2)
    ]
    return not problems, problems


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["results"]


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--retry-list":
        print(" ".join(str(q) for q in retry_list(load(argv[1]))))
        return 0
    results = load(argv[0])
    if len(argv) > 1:
        results = merge(results, load(argv[1]))
    summary = summarize(results)
    ok, problems = verdict(summary)
    left = retry_list(results)
    if left:
        ok = False
        problems.append(f"still unavailable after the retry: Q{', Q'.join(map(str, left))}")
    print("  ".join(f"{m} {summary[m]:.2f}" for m in METRICS), f"(n={summary['n']})")
    print("PASS" if ok else "FAIL")
    for p in problems:
        print(f"  - {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
