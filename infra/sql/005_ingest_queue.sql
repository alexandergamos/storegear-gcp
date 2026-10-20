-- 005_ingest_queue.sql · SMO-19 · the ingestion queue (ADR-011): one row per version of a manual
-- Idempotency: the same file with the same content can only be queued once (UNIQUE file_id + content_hash + action).
-- content_hash = Drive's md5Checksum (the md5 of the bytes), so the Drive sync (SMO-20) can dedupe without downloading.
-- Requeue a dead job (as Alexander): UPDATE ingest_queue SET status='queued', attempts=0, next_attempt_at=now() WHERE id=...;
--   uv run python infra/sql/apply.py infra/sql/005_ingest_queue.sql

CREATE TABLE IF NOT EXISTS ingest_queue (
  id              BIGSERIAL PRIMARY KEY,
  file_id         TEXT NOT NULL,                          -- Drive file id
  file_name       TEXT NOT NULL,
  access_level    TEXT NOT NULL DEFAULT 'staff' CHECK (access_level IN ('staff', 'manager')),
  action          TEXT NOT NULL DEFAULT 'upsert' CHECK (action IN ('upsert', 'delete')),
  content_hash    TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'superseded', 'dead')),
  attempts        INT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_at      TIMESTAMPTZ,
  claimed_by      TEXT,
  last_error      TEXT,
  stats           JSONB,                                  -- pages, coverage, sections, chunks, quarantined, seconds
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (file_id, content_hash, action)
);
CREATE INDEX IF NOT EXISTS ingest_queue_ready_idx ON ingest_queue (status, next_attempt_at);

GRANT SELECT, INSERT, UPDATE ON ingest_queue TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT USAGE, SELECT ON SEQUENCE ingest_queue_id_seq TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT SELECT, UPDATE (status, attempts, next_attempt_at) ON ingest_queue TO "{{ADMIN_EMAIL}}";
