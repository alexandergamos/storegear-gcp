-- 008_api_rate.sql · SMO-22 · per-user rate-limit counters for sg-api (ADR-014)
-- Fixed windows: one row per user per minute and per day; sg-api increments with INSERT ... ON CONFLICT.
-- Requires the IAM database user sg-api@storegear-prod-ag26.iam (Cloud SQL > Users > Add > Cloud IAM).
--   uv run python infra/sql/apply.py infra/sql/008_api_rate.sql

CREATE TABLE IF NOT EXISTS api_rate (
  uid          TEXT NOT NULL,                 -- Identity Platform user id (from the verified token)
  kind         TEXT NOT NULL CHECK (kind IN ('min', 'day')),
  window_start TIMESTAMPTZ NOT NULL,
  count        INT NOT NULL,
  PRIMARY KEY (uid, kind, window_start)
);

GRANT USAGE ON SCHEMA public TO "sg-api@storegear-prod-ag26.iam";
GRANT SELECT, INSERT, UPDATE, DELETE ON api_rate TO "sg-api@storegear-prod-ag26.iam";
