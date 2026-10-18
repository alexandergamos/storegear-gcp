"""SMO-17 · Parse every manual to Markdown (ADR-009): Gemini first, coverage check, Document AI fallback.

    uv run python ingestion/parse_manuals.py                 # all PDFs in data/pdf/full/
    uv run python ingestion/parse_manuals.py --only ignite2  # one manual (file stem contains the text)

For each PDF: pages in batches of BATCH -> Gemini 3.8 Flash (prompt from parser_test.py) -> coverage vs the raw
page text -> below THRESHOLD the batch is re-parsed with Document AI Layout Parser. Output:
data/parsed/full/<stem>.md with "<!-- page N -->" markers, and data/parsed/full/<stem>.report.json.

Coverage = share of the raw text's 6-letter shingles (letters only, spaces removed) found in the output. Removing
spaces makes it immune to PDFs whose raw extraction glues words together (the word metric gave 56 % on Ignite 2
for BOTH parsers).
"""
import argparse
import io
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).parent))
from parser_test import layout_to_markdown, parse_gemini_bytes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "pdf" / "full"
OUT = ROOT / "data" / "parsed" / "full"
BATCH = 4
THRESHOLD = 0.95
PROCESSOR = "8a9ba69484bf2664"


def shingles(text: str, k: int = 6) -> set[str]:
    letters = re.sub(r"[^a-záéíóúñü0-9]", "", text.lower())
    return {letters[i:i + k] for i in range(max(len(letters) - k + 1, 0))}


def coverage(raw: str, parsed: str) -> float:
    ref = shingles(raw)
    return 1.0 if not ref else len(ref & shingles(parsed)) / len(ref)


def batch_pdf(reader: PdfReader, pages: list[int]) -> bytes:
    w = PdfWriter()
    for p in pages:
        w.add_page(reader.pages[p])
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def parse_docai_bytes(data: bytes) -> str:
    from google.api_core.client_options import ClientOptions
    from google.cloud import documentai
    client = documentai.DocumentProcessorServiceClient(client_options=ClientOptions(api_endpoint="eu-documentai.googleapis.com"))
    req = documentai.ProcessRequest(name=client.processor_path("storegear-prod-ag26", "eu", PROCESSOR),
                                    raw_document=documentai.RawDocument(content=data, mime_type="application/pdf"))
    return layout_to_markdown(client.process_document(request=req).document)


def parse_batch(job: dict) -> dict:
    """One batch: Gemini, coverage check, Document AI fallback. Runs in worker threads, so it only touches the
    pre-cut bytes and raw text (pypdf readers are not thread-safe)."""
    pages, data, raw = job["pages"], job["data"], job["raw"]
    t0 = time.time()
    for attempt in range(3):
        try:
            md = parse_gemini_bytes(data)
            break
        except Exception as e:  # noqa: BLE001
            md = ""
            err = str(e)[:120]
            time.sleep(2 ** attempt)
    cov = coverage(raw, md)
    used = "gemini"
    if cov < THRESHOLD:
        md_d = parse_docai_bytes(data)
        cov_d = coverage(raw, md_d)
        if cov_d > cov:
            md, used, cov = md_d, "docai", cov_d
    return {"pages": [p + 1 for p in pages], "parser": used, "coverage": round(cov, 3), "seconds": round(time.time() - t0, 1), "md": md}


def parse_manual(pdf: Path) -> None:
    reader = PdfReader(str(pdf))
    batches = [list(range(i, min(i + BATCH, len(reader.pages)))) for i in range(0, len(reader.pages), BATCH)]
    jobs = [{"pages": b, "data": batch_pdf(reader, b), "raw": "\n".join(reader.pages[p].extract_text() or "" for p in b)}
            for b in batches]  # cut every batch in this thread first
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(parse_batch, jobs))
    md = "\n\n".join(f"<!-- page {r['pages'][0]} -->\n{r['md']}" for r in results)
    (OUT / f"{pdf.stem}.md").write_text(md, encoding="utf-8")
    report = [{k: v for k, v in r.items() if k != "md"} for r in results]
    (OUT / f"{pdf.stem}.report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    covs = [r["coverage"] for r in results]
    fallback = sum(r["parser"] == "docai" for r in results)
    print(f"{pdf.stem:40} {len(reader.pages):4} pages · coverage min {min(covs):.2f} avg {sum(covs) / len(covs):.2f} · docai fallback {fallback}/{len(results)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(SRC.glob("*.pdf")):
        if a.only in pdf.stem and not (OUT / f"{pdf.stem}.md").exists():
            try:
                parse_manual(pdf)
            except Exception as e:  # noqa: BLE001  one bad manual must not stop the rest
                print(f"{pdf.stem:40} FAILED: {type(e).__name__}: {str(e)[:150]}")
