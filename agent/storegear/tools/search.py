"""Hybrid catalog search: one SQL query = dense (pgvector) + Spanish keywords (IDF-weighted) + parent-level RRF.

Ported 1:1 from n8n "StoreGear - Hybrid Search (pgvector)" (ADR-004): same SQL, same parameters
(24 candidates per branch, RRF k=60, dense weight 1.0, keyword 0.5), same output (top 5 parent sections
wrapped in <manual> tags). No reranker: the n8n eval showed no loss without it.

Security:
- `role` is NOT a tool argument the model can set. The agent passes it from the verified login (SMO-22);
  the model never decides whether it sees manager-only documents.
- Retrieved text is wrapped in <manual> tags and any tag inside it is neutralised ("spotlighting"), so a
  manual can't close the tag and pose as instructions (prompt-injection defence, same as n8n rule 10).

Connection: IAM database auth through the Cloud SQL Python Connector. In the cloud it runs as the attached
service account (sg-agent). Locally it uses your login, or impersonates sg-agent when
STOREGEAR_IMPERSONATE_SA is set, to test with exactly the agent's permissions.
"""
from __future__ import annotations

import atexit
import os
import re
import threading
import time

import google.auth
import sqlalchemy
from google import genai
from google.auth import impersonated_credentials
from google.cloud.sql.connector import Connector
from google.genai import types

# Project ID (not number): Agent Runtime sets GOOGLE_CLOUD_PROJECT to the project NUMBER, and Cloud SQL
# connection names require the ID ("The Cloud SQL instance does not exist" otherwise).
PROJECT = os.getenv("STOREGEAR_PROJECT_ID", "storegear-prod-ag26")
INSTANCE = os.getenv("STOREGEAR_DB_INSTANCE", f"{PROJECT}:europe-west1:sg-catalog")
DATABASE = os.getenv("STOREGEAR_DB_NAME", "storegear")
EMBED_MODEL = os.getenv("STOREGEAR_EMBED_MODEL", "gemini-embedding-2")  # ADR-005
EMBED_LOCATION = os.getenv("STOREGEAR_EMBED_LOCATION", "eu")
TOP_K = 8                  # n8n topK
FETCH_K = TOP_K * 3        # candidates per branch (dense / keyword)
# Which catalog tables to read: "" = live, "_v2" = the re-parsed side tables under evaluation (SMO-17).
CATALOG_SUFFIX = os.getenv("STOREGEAR_CATALOG_SUFFIX", "")
RETURN_N = int(os.getenv("STOREGEAR_RETURN_N", "5"))   # parents handed to the model
MAX_PER_MANUAL = 3         # diversity: a comparison ("A vs B") must not get 5 sections of A
SCOPES = ["https://www.googleapis.com/auth/sqlservice.login", "https://www.googleapis.com/auth/cloud-platform"]

HYBRID_SQL = """
WITH params AS (
  SELECT CAST(:qv AS vector) AS qv, CAST(:qt AS text) AS qt, CAST(:k AS int) AS k, CAST(:role AS text) AS role
),
allowed AS (
  SELECT c.* FROM catalog_chunks c, params p
   WHERE c.access_level = 'staff' OR (p.role = 'manager' AND c.access_level = 'manager')
),
dense AS (
  SELECT a.child_id, a.parent_id, row_number() OVER (ORDER BY a.embedding <=> p.qv) AS r
    FROM allowed a, params p
   WHERE a.embedding IS NOT NULL
   ORDER BY a.embedding <=> p.qv
   LIMIT (SELECT k FROM params)
),
terms AS (
  SELECT DISTINCT lx FROM params, unnest(tsvector_to_array(to_tsvector('spanish', params.qt))) AS lx
),
total AS (SELECT GREATEST(count(*), 1)::float AS n FROM catalog_chunks),
tw AS (
  SELECT to_tsquery('simple', quote_literal(t.lx)) AS tq,
         ln((SELECT n FROM total) / GREATEST(1, (SELECT count(*) FROM catalog_chunks d
             WHERE d.search_vector @@ to_tsquery('simple', quote_literal(t.lx))))) + 0.01 AS idf
    FROM terms t
),
q AS (
  SELECT to_tsquery('simple', coalesce(nullif(array_to_string(ARRAY(SELECT quote_literal(lx) FROM terms), ' | '), ''), '')) AS tsq
),
sparse_scored AS (
  SELECT a.child_id, a.parent_id,
         ts_rank_cd(a.search_vector, q.tsq) AS rank,
         (SELECT count(*) FROM tw WHERE a.search_vector @@ tw.tq) AS matched,
         (SELECT coalesce(sum(tw.idf), 0) FROM tw WHERE a.search_vector @@ tw.tq) AS idf_score
    FROM allowed a, q
   WHERE a.search_vector @@ q.tsq
),
sparse AS (
  SELECT child_id, parent_id, row_number() OVER (ORDER BY idf_score DESC, rank DESC) AS r
    FROM sparse_scored
   WHERE matched >= LEAST(2, (SELECT count(*) FROM terms))
   ORDER BY idf_score DESC, rank DESC
   LIMIT (SELECT k FROM params)
),
dp AS (
  SELECT parent_id, row_number() OVER (ORDER BY min(r)) AS pr, (array_agg(child_id ORDER BY r))[1] AS best_child
    FROM dense GROUP BY parent_id
),
sp AS (
  SELECT parent_id, row_number() OVER (ORDER BY min(r)) AS pr, (array_agg(child_id ORDER BY r))[1] AS best_child
    FROM sparse GROUP BY parent_id
),
fused AS (
  SELECT coalesce(dp.parent_id, sp.parent_id) AS parent_id,
         coalesce(1.0 / (60 + dp.pr), 0) + coalesce(0.5 / (60 + sp.pr), 0) AS score,
         coalesce(dp.best_child, sp.best_child) AS best_child,
         concat_ws(',', 'dense#' || dp.pr, 'sparse#' || sp.pr) AS sources
    FROM dp FULL OUTER JOIN sp ON dp.parent_id = sp.parent_id
   ORDER BY score DESC
   LIMIT 20
)
SELECT f.parent_id, round(f.score::numeric, 6)::float AS rrf_score, c.file_name, c.header_path,
       coalesce(cp.parent_context, (SELECT string_agg(x.chunk_text, E'\\n' ORDER BY x.id)
                                      FROM catalog_chunks x WHERE x.parent_id = f.parent_id)) AS parent_context,
       f.sources
  FROM fused f
  JOIN catalog_chunks c ON c.child_id = f.best_child
  LEFT JOIN catalog_parents cp ON cp.parent_id = f.parent_id
 ORDER BY f.score DESC
"""

NO_RESULTS = "No se encontraron chunks relevantes en el catalogo para esta consulta."
_TAG = re.compile(r"</?manual[^>]*>", re.IGNORECASE)

_lock = threading.Lock()
_engine: sqlalchemy.Engine | None = None
_genai: genai.Client | None = None


def _credentials():
    base, _ = google.auth.default(scopes=SCOPES)
    sa = os.getenv("STOREGEAR_IMPERSONATE_SA")
    if not sa:
        return base, None
    return impersonated_credentials.Credentials(source_credentials=base, target_principal=sa, target_scopes=SCOPES), sa


def _db_user(creds, sa: str | None) -> str:
    """IAM DB user name: '<sa-name>@<project>.iam' for service accounts, the email for people."""
    principal = sa or os.getenv("STOREGEAR_DB_USER") or getattr(creds, "service_account_email", None)
    if not principal or principal == "default":
        raise RuntimeError("Set STOREGEAR_DB_USER (your email) or STOREGEAR_IMPERSONATE_SA for local runs")
    return principal.removesuffix(".gserviceaccount.com")


def engine() -> sqlalchemy.Engine:
    """One pooled engine per process: opening a Cloud SQL connection costs ~0.5-1 s (TLS + IAM token)."""
    global _engine
    with _lock:
        if _engine is None:
            creds, sa = _credentials()
            user = _db_user(creds, sa)
            connector = Connector(credentials=creds, refresh_strategy="lazy")
            atexit.register(connector.close)  # clean shutdown (avoids aiohttp "unclosed session" warnings)
            _engine = sqlalchemy.create_engine(
                "postgresql+pg8000://",
                creator=lambda: connector.connect(INSTANCE, "pg8000", user=user, db=DATABASE, enable_iam_auth=True),
                pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800,
            )
        return _engine


def embed_query(text: str) -> list[float]:
    global _genai
    if _genai is None:
        _genai = genai.Client(vertexai=True, project=PROJECT, location=EMBED_LOCATION)
    r = _genai.models.embed_content(model=EMBED_MODEL, contents=text,
                                    config=types.EmbedContentConfig(output_dimensionality=1024, task_type="RETRIEVAL_QUERY"))
    return r.embeddings[0].values


def hybrid_search(query: str, role: str = "staff", top_n: int = RETURN_N) -> list[dict]:
    """Raw ranked parents (for evals and debugging). `role` comes from the verified login, never from the model."""
    role = role if role in ("staff", "manager") else "staff"
    qv = "[" + ",".join(f"{x:.7f}" for x in embed_query(query)) + "]"
    with engine().connect() as conn:
        sql = HYBRID_SQL.replace("catalog_chunks", f"catalog_chunks{CATALOG_SUFFIX}").replace("catalog_parents", f"catalog_parents{CATALOG_SUFFIX}")
        rows = conn.execute(sqlalchemy.text(sql), {"qv": qv, "qt": query, "k": FETCH_K, "role": role}).mappings().all()
    return diversify([dict(r) for r in rows], top_n)


def diversify(rows: list[dict], top_n: int, cap: int = MAX_PER_MANUAL) -> list[dict]:
    """Keep RRF order but take at most `cap` sections per manual, then fill any gap in order.
    Added 2026-10-17 (SMO-12): without it, "Instinct 3 vs Vantage M2" returned 5 Vantage M2 sections."""
    picked, per_file = [], {}
    for r in rows:
        if per_file.get(r["file_name"], 0) < cap:
            picked.append(r)
            per_file[r["file_name"]] = per_file.get(r["file_name"], 0) + 1
        if len(picked) == top_n:
            return picked
    rest = [r for r in rows if r not in picked]
    return (picked + rest)[:top_n]


def format_for_agent(rows: list[dict]) -> str:
    """Spotlighting: each parent inside <manual fuente=... seccion=...>; nested tags neutralised."""
    if not rows:
        return NO_RESULTS
    parts = []
    for r in rows:
        src = (r["file_name"] or "").replace('"', "")
        sec = (r["header_path"] or "").replace('"', "")
        body = _TAG.sub("[etiqueta eliminada]", r["parent_context"] or "")
        file_id = (r["parent_id"] or "").split("::", 1)[0]  # Drive fileId: key for consultar_precio_stock
        parts.append(f'<manual fuente="{src}" seccion="{sec}" fileId="{file_id}">\n{body}\n</manual>')
    return "\n\n".join(parts)


def search_catalog(query: str, role: str = "staff") -> str:
    t = time.time()
    text = format_for_agent(hybrid_search(query, role))
    if os.getenv("STOREGEAR_DEBUG"):
        print(f"[search] {time.time() - t:.2f}s · {query[:60]!r}")
    return text
