"""SMO-11 · Embed the n8n catalog export with a Google embedding model, cached to data/ (git-ignored).

    uv run python ingestion/embed_export.py gemini-embedding-001     # europe-west1, batches of 25
    uv run python ingestion/embed_export.py gemini-embedding-2       # eu endpoint, one text per request

Output: data/emb_<model>.npy (float32, one row per chunk, same order as data/catalog_chunks.csv)
        data/emb_<model>.ids.json (child_id per row)

Contextual embeddings (2026-10-17): we embed "header_path + chunk_text", not chunk_text alone. Only 2-3 % of
chunks name their own product; the header always does ("Polar Ignite 2.pdf > ..."), so without it sibling
manuals (Polar Grit X2 vs Ignite 2) look alike to the embedding.

Gotcha found 2026-10-17: gemini-embedding-2 treats a list of texts as ONE multimodal input and returns ONE
vector, so batching silently merges chunks. It must be called one text at a time.
"""
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from google import genai
from google.genai import types

PROJECT = "storegear-prod-ag26"
DIMS = 1024  # must match catalog_chunks.embedding vector(1024)
MODELS = {  # model -> (location, batch size)
    "gemini-embedding-001": ("europe-west1", 25),
    "gemini-embedding-2": ("eu", 1),
}


def load_chunks(path: str = "data/catalog_chunks.csv") -> list[dict]:
    csv.field_size_limit(2**31 - 1)
    with open(path, encoding="utf-8", newline="") as fh:
        return [{"child_id": r["child_id"], "text": r["header_path"] + "\n" + r["chunk_text"]} for r in csv.DictReader(fh)]


def embed_batch(client, model: str, texts: list[str], task: str) -> list[list[float]]:
    for attempt in range(6):  # backoff on quota (429) / transient errors
        try:
            r = client.models.embed_content(
                model=model, contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=DIMS, task_type=task))
            if len(r.embeddings) != len(texts):
                raise RuntimeError(f"{model} returned {len(r.embeddings)} vectors for {len(texts)} texts")
            return [e.values for e in r.embeddings]
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            print(f"  retry in {wait}s: {str(e)[:80]}")
            time.sleep(wait)
    raise RuntimeError("too many retries")


def embed_texts(model: str, texts: list[str], task: str, workers: int = 12) -> np.ndarray:
    location, size = MODELS[model]
    client = genai.Client(vertexai=True, project=PROJECT, location=location)
    batches = [texts[i:i + size] for i in range(0, len(texts), size)]
    out: list = [None] * len(batches)
    done = 0
    t0 = time.time()

    def work(i):
        out[i] = embed_batch(client, model, batches[i], task)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(work, range(len(batches))):
            done += 1
            if done % max(1, len(batches) // 10) == 0:
                print(f"  {done}/{len(batches)} batches · {time.time() - t0:.0f}s")
    vecs = np.array([v for b in out for v in b], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)  # unit length: cosine = dot product


if __name__ == "__main__":
    model = sys.argv[1]
    src = sys.argv[2] if len(sys.argv) > 2 else "data/catalog_chunks.csv"   # v2: data/catalog_v2/chunks.csv
    tag = model + ("_v2" if "catalog_v2" in src else "")
    chunks = load_chunks(src)
    print(f"{model}: embedding {len(chunks)} chunks")
    vecs = embed_texts(model, [c["text"] for c in chunks], "RETRIEVAL_DOCUMENT")
    np.save(f"data/emb_{tag}.npy", vecs)
    json.dump([c["child_id"] for c in chunks], open(f"data/emb_{tag}.ids.json", "w"))
    print(f"saved data/emb_{tag}.npy {vecs.shape}")
