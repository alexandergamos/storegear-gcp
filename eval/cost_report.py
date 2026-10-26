"""SMO-26 · Weekly cost report (ADR-019): what the ANSWER lines estimate vs what Google billed.

    uv run python eval/cost_report.py            # last 7 days
    uv run python eval/cost_report.py --days 30

Estimated: the sum of cost_eur over the Google Cloud agent's ANSWER lines (sg-api, Cloud Logging).
Billed: the Gemini 3.8 Flash SKUs of this project in the billing export (BigQuery, dataset billing_export), by SKU.
The bill also holds eval runs, which don't go through sg-api, so compare weeks without evals; a gap over 15 %
means the price table in api/cost.py is wrong.
"""
import argparse
import json
import shutil
import subprocess
import urllib.request

PROJECT = "storegear-prod-ag26"
BILLING_TABLE = f"{PROJECT}.billing_export.gcp_billing_export_v1_015A61_AA5863_92E56E"
TOLERANCE_PCT = 15.0


def summarize(lines: list[dict]) -> dict:
    priced = [x for x in lines if x.get("event") == "ANSWER" and x.get("agent") == "gcp"]
    total = round(sum(x.get("cost_eur") or 0.0 for x in priced), 7)
    return {"answers": len(priced), "estimated_eur": total,
            "per_answer_eur": round(total / len(priced), 7) if priced else None,
            "blocked": sum(1 for x in priced if x.get("guard"))}


def compare(estimated_eur: float, billed_eur: float) -> tuple[float | None, bool]:
    """(difference in % of the bill, within tolerance). Negative = the estimate is below the bill."""
    if not billed_eur:
        return None, False
    diff = (estimated_eur - billed_eur) / billed_eur * 100
    return diff, abs(diff) <= TOLERANCE_PCT


def gcloud(*args: str) -> list[str]:
    """The gcloud command with its full path: on Windows it is gcloud.cmd, which a bare "gcloud" doesn't find."""
    return [shutil.which("gcloud") or "gcloud", *args]


def _token() -> str:
    return subprocess.run(gcloud("auth", "print-access-token"), capture_output=True, text=True).stdout.strip()


def answer_lines(days: int) -> list[dict]:
    # the days are bounded by --freshness: Cloud Logging rejects a relative "-P7D" inside the filter
    flt = 'resource.type="cloud_run_revision" AND resource.labels.service_name="sg-api" AND jsonPayload.event="ANSWER"'
    r = subprocess.run(gcloud("logging", "read", flt, f"--project={PROJECT}", "--format=json", "--limit=100000",
                              f"--freshness={days}d"), capture_output=True, text=True)
    if r.returncode != 0:   # a failed read must stop the report, never show up as "0 answers"
        raise SystemExit(f"gcloud logging read failed: {r.stderr.strip()[:300]}")
    return [e["jsonPayload"] for e in json.loads(r.stdout or "[]") if "jsonPayload" in e]


def billed_query(days: int) -> str:
    """Gemini 3.8 Flash in this project, matched by SKU: Google renamed the service ("Vertex AI" is now billed as
    "Agent Platform Model Garden"). Gross cost, like the estimate; the API-key billing (n8n's side) is left out."""
    return f"""SELECT IFNULL(SUM(cost), 0) FROM `{BILLING_TABLE}`
            WHERE project.id = '{PROJECT}' AND sku.description LIKE '%Gemini 3.8 Flash%'
              AND service.description NOT LIKE 'Gemini API%'
              AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)"""


def billed_eur(days: int) -> float:
    q = billed_query(days)
    req = urllib.request.Request(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries",
                                 data=json.dumps({"query": q, "useLegacySql": False}).encode(),
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    rows = json.load(urllib.request.urlopen(req)).get("rows", [])
    return float(rows[0]["f"][0]["v"]) if rows else 0.0


def main(days: int) -> None:
    s = summarize(answer_lines(days))
    billed = billed_eur(days)
    diff, ok = compare(s["estimated_eur"], billed)
    print(f"Last {days} days, Google Cloud agent")
    print(f"  answers (via sg-api):     {s['answers']}  ({s['blocked']} stopped by a guardrail)")
    print(f"  estimated:                {s['estimated_eur']:.4f} EUR  ·  per answer {s['per_answer_eur'] or 0:.5f} EUR")
    print(f"  billed (Gemini 3.8 Flash): {billed:.4f} EUR  (includes eval runs)")
    print("  difference:               " + (f"{diff:+.1f} % ({'within' if ok else 'beyond'} ±{TOLERANCE_PCT:.0f} %)" if diff is not None else "nothing billed"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    main(ap.parse_args().days)
