-- 009_web_demo.sql · SMO-35 · sg-api for the web demo (ADR-017)
--   uv run python infra/sql/apply.py infra/sql/009_web_demo.sql

-- GET /catalog/models: model names from the staff manuals (file names only, never chunk text to the client)
GRANT SELECT ON catalog_chunks TO "sg-api@storegear-prod-ag26.iam";

-- Blind comparisons: which agent is A in each conversation (never sent before reveal) and one vote per question.
-- Deleted once the SMO-29 report is written (runbook).
CREATE TABLE IF NOT EXISTS compare_conversations (
  id             TEXT PRIMARY KEY,
  uid            TEXT NOT NULL,                                   -- Identity Platform user id (verified token)
  mapping_a      TEXT NOT NULL CHECK (mapping_a IN ('gcp', 'n8n')),
  gcp_session_id TEXT,                                            -- Agent Runtime session reused for follow-ups
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  revealed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS compare_votes (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES compare_conversations(id),
  uid             TEXT NOT NULL,
  question        TEXT NOT NULL,                                  -- already PII-masked
  a_total_ms      INT,
  b_total_ms      INT,
  a_error         BOOL NOT NULL DEFAULT false,
  b_error         BOOL NOT NULL DEFAULT false,
  vote            TEXT CHECK (vote IN ('A', 'B', 'tie')),
  voted_at        TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON compare_conversations, compare_votes TO "sg-api@storegear-prod-ag26.iam";
