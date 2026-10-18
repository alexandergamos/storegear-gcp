"""SMO-11 · Load the n8n catalog export + Google embeddings into Cloud SQL.

    uv run python ingestion/load_catalog.py gemini-embedding-001

Connects AS sg-ingestion (IAM database auth via impersonation): the only identity allowed to write the
catalog (ADR-002). Idempotent: upserts on child_id / parent_id, so it can be re-run with another model.
"""
import csv
import json
import sys
import time

import google.auth
import numpy as np
from google.auth import impersonated_credentials
from google.cloud.sql.connector import Connector

PROJECT = "storegear-prod-ag26"
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
SA = f"sg-ingestion@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/sqlservice.login", "https://www.googleapis.com/auth/cloud-platform"]
BATCH = 200

UPSERT_CHUNKS = """
INSERT INTO catalog_chunks{S} (child_id, parent_id, file_id, file_name, header_path, chunk_text,
                            product_category, access_level, embedding, updated_at)
SELECT * , now() FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::text[], %s::text[],
                             %s::text[], %s::text[], %s::vector[])
ON CONFLICT (child_id) DO UPDATE SET
  parent_id = EXCLUDED.parent_id, file_id = EXCLUDED.file_id, file_name = EXCLUDED.file_name,
  header_path = EXCLUDED.header_path, chunk_text = EXCLUDED.chunk_text,
  product_category = EXCLUDED.product_category, access_level = EXCLUDED.access_level,
  embedding = EXCLUDED.embedding, updated_at = now()
"""
UPSERT_PARENTS = """
INSERT INTO catalog_parents{S} (parent_id, file_id, header_path, parent_context, updated_at)
SELECT *, now() FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[])
ON CONFLICT (parent_id) DO UPDATE SET
  file_id = EXCLUDED.file_id, header_path = EXCLUDED.header_path,
  parent_context = EXCLUDED.parent_context, updated_at = now()
"""


def read_csv(path: str) -> list[dict]:
    csv.field_size_limit(2**31 - 1)
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main(model: str, v2: bool) -> None:
    suffix = "_v2" if v2 else ""
    chunks = read_csv("data/catalog_v2/chunks.csv" if v2 else "data/catalog_chunks.csv")
    parents = read_csv("data/catalog_v2/parents.csv" if v2 else "data/catalog_parents.csv")
    vecs = np.load(f"data/emb_{model}{suffix}.npy")
    ids = json.load(open(f"data/emb_{model}{suffix}.ids.json"))
    assert ids == [c["child_id"] for c in chunks], "embedding file doesn't match the CSV order"
    as_vec = lambda v: "[" + ",".join(f"{x:.7f}" for x in v) + "]"  # noqa: E731  pgvector text format

    base, _ = google.auth.default(scopes=SCOPES)
    creds = impersonated_credentials.Credentials(source_credentials=base, target_principal=SA, target_scopes=SCOPES)
    t0 = time.time()
    with Connector(credentials=creds) as connector:
        conn = connector.connect(INSTANCE, "pg8000", user=f"sg-ingestion@{PROJECT}.iam", db="storegear", enable_iam_auth=True)
        cur = conn.cursor()
        for i in range(0, len(parents), BATCH):
            b = parents[i:i + BATCH]
            cur.execute(UPSERT_PARENTS.replace('{S}', suffix), ([p["parent_id"] for p in b], [p["file_id"] for p in b],
                                         [p["header_path"] for p in b], [p["parent_context"] for p in b]))
        print(f"parents: {len(parents)} upserted")
        for i in range(0, len(chunks), BATCH):
            b, v = chunks[i:i + BATCH], vecs[i:i + BATCH]
            cur.execute(UPSERT_CHUNKS.replace('{S}', suffix), (
                [c["child_id"] for c in b], [c["parent_id"] for c in b], [c["file_id"] for c in b],
                [c["file_name"] for c in b], [c["header_path"] for c in b], [c["chunk_text"] for c in b],
                [c["product_category"] or None for c in b], [c["access_level"] or "staff" for c in b],
                [as_vec(x) for x in v]))
            if (i // BATCH) % 10 == 0:
                print(f"  chunks {i + len(b)}/{len(chunks)} · {time.time() - t0:.0f}s")
        conn.commit()
        cur.execute(f"SELECT count(*), count(embedding), count(DISTINCT parent_id) FROM catalog_chunks{suffix}")
        n, n_emb, n_par = cur.fetchone()
        cur.execute(f"SELECT count(*) FROM catalog_chunks{suffix} c WHERE NOT EXISTS "
                    f"(SELECT 1 FROM catalog_parents{suffix} p WHERE p.parent_id = c.parent_id)")
        orphans = cur.fetchone()[0]
        print(f"done in {time.time() - t0:.0f}s · chunks {n} · with embedding {n_emb} · parents {n_par} · orphans {orphans}")
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1], "--v2" in sys.argv)
