-- 001_schema.sql · SMO-10 · catalog schema for hybrid search (ADR-004)
-- Mirrors the n8n tables (catalog_chunks, catalog_parents) so the hybrid search query ports unchanged.
-- Run as the built-in `postgres` admin (CREATE EXTENSION needs cloudsqlsuperuser):
--   uv run python infra/sql/apply.py infra/sql/001_schema.sql
-- Idempotent: safe to run twice.

-- pgvector: the `vector` type and distance operators (<=> = cosine distance)
CREATE EXTENSION IF NOT EXISTS vector;

-- Child chunks: what search ranks. One row per small passage of a manual.
CREATE TABLE IF NOT EXISTS catalog_chunks (
  id               BIGSERIAL PRIMARY KEY,                 -- insertion order; used to rebuild parent text
  child_id         TEXT NOT NULL UNIQUE,                  -- '<fileId>::<section>::<n>' from ingestion
  parent_id        TEXT NOT NULL,                         -- the section this chunk belongs to
  file_id          TEXT NOT NULL,                         -- Drive file id of the manual
  file_name        TEXT,
  header_path      TEXT,                                  -- 'Manual > Chapter > Section'
  chunk_text       TEXT NOT NULL,
  product_category TEXT,
  access_level     TEXT NOT NULL DEFAULT 'staff' CHECK (access_level IN ('staff', 'manager')),
  embedding        vector(1024),                          -- dimension confirmed in SMO-11 (embedding model ADR)
  -- Spanish full-text search: stemmed lexemes, so 'baterías' matches 'batería'. Generated, never written by the app.
  -- ASSUMPTION: same expression as n8n ("generated from chunk_text"); verify against the n8n DDL in SMO-11.
  search_vector    tsvector GENERATED ALWAYS AS (to_tsvector('spanish', coalesce(chunk_text, ''))) STORED,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Parent sections: what the agent reads. Search ranks children, then returns the whole parent for context.
CREATE TABLE IF NOT EXISTS catalog_parents (
  parent_id      TEXT PRIMARY KEY,
  file_id        TEXT,
  header_path    TEXT,
  parent_context TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS catalog_chunks_search_idx ON catalog_chunks USING gin (search_vector);        -- keyword search
CREATE INDEX IF NOT EXISTS catalog_chunks_embedding_idx ON catalog_chunks USING hnsw (embedding vector_cosine_ops); -- vector search
CREATE INDEX IF NOT EXISTS catalog_chunks_parent_idx ON catalog_chunks (parent_id);
CREATE INDEX IF NOT EXISTS catalog_chunks_file_idx ON catalog_chunks (file_id);
CREATE INDEX IF NOT EXISTS catalog_parents_file_idx ON catalog_parents (file_id);

-- Least privilege (ADR-002): IAM database users, no passwords.
--   sg-agent      → read only (the agent can never change the catalog, even if prompt-injected)
--   sg-ingestion  → read + write (the pipeline maintains the catalog)
GRANT USAGE ON SCHEMA public TO "sg-agent@storegear-prod-ag26.iam", "sg-ingestion@storegear-prod-ag26.iam";
GRANT SELECT ON catalog_chunks, catalog_parents TO "sg-agent@storegear-prod-ag26.iam";
GRANT SELECT, INSERT, UPDATE, DELETE ON catalog_chunks, catalog_parents TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT USAGE, SELECT ON SEQUENCE catalog_chunks_id_seq TO "sg-ingestion@storegear-prod-ag26.iam";
-- Alexander (IAM user): read access for inspection from Cloud SQL Studio / scripts
GRANT USAGE ON SCHEMA public TO "{{ADMIN_EMAIL}}";
GRANT SELECT ON catalog_chunks, catalog_parents TO "{{ADMIN_EMAIL}}";
