-- 004_quarantine.sql · SMO-18 · sections flagged by the injection check wait here for review (ADR-010)
-- sg-agent gets NO grant: the agent can never read quarantined text, even by mistake.
-- Review (as Alexander): UPDATE catalog_quarantine SET status = 'approved', reviewed_at = now() WHERE parent_id = '...';
--   uv run python infra/sql/apply.py infra/sql/004_quarantine.sql

CREATE TABLE IF NOT EXISTS catalog_quarantine (
  parent_id      TEXT PRIMARY KEY,
  file_id        TEXT NOT NULL,
  header_path    TEXT NOT NULL,
  parent_context TEXT NOT NULL,
  text_sha256    TEXT NOT NULL,                        -- a changed section is re-checked, an approval doesn't carry over
  detector       TEXT NOT NULL,                        -- regex | gemini | regex+gemini | error (fail closed)
  score          REAL,
  span           TEXT,                                 -- the suspicious phrase, for a fast review
  status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  checked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at    TIMESTAMPTZ
);

GRANT SELECT, INSERT, UPDATE ON catalog_quarantine TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT SELECT, UPDATE (status, reviewed_at) ON catalog_quarantine TO "{{ADMIN_EMAIL}}";
