-- 006_sync_and_v3.sql · SMO-20 (ADR-012)
-- 1) Queue rows get a target: '' = the live catalog, '_v3' = the side tables of a full rebuild. The version key now
--    includes it, so rebuilding a file never collides with its live job.
-- 2) Empty side tables for the full rebuild by the Google pipeline (same structure, indexes and grants as live).
--   uv run python infra/sql/apply.py infra/sql/006_sync_and_v3.sql

ALTER TABLE ingest_queue ADD COLUMN IF NOT EXISTS target TEXT NOT NULL DEFAULT '';
ALTER TABLE ingest_queue DROP CONSTRAINT IF EXISTS ingest_queue_file_id_content_hash_action_key;
ALTER TABLE ingest_queue ADD CONSTRAINT ingest_queue_version_key UNIQUE (file_id, content_hash, action, target);

CREATE TABLE IF NOT EXISTS catalog_chunks_v3 (LIKE catalog_chunks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS catalog_parents_v3 (LIKE catalog_parents INCLUDING ALL);

GRANT SELECT ON catalog_chunks_v3, catalog_parents_v3 TO "sg-agent@storegear-prod-ag26.iam";
GRANT SELECT, INSERT, UPDATE, DELETE ON catalog_chunks_v3, catalog_parents_v3 TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT SELECT ON catalog_chunks_v3, catalog_parents_v3 TO "{{ADMIN_EMAIL}}";
