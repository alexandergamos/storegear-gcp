-- 002_catalog_v2.sql · SMO-17 · side tables for the re-parsed, table-aware catalog
-- Same structure, indexes and generated Spanish search column as the live tables (LIKE ... INCLUDING ALL).
-- The live catalog stays untouched; the agent switches only after the benchmark + eval hold (swap in 003).
--   uv run python infra/sql/apply.py infra/sql/002_catalog_v2.sql

CREATE TABLE IF NOT EXISTS catalog_chunks_v2 (LIKE catalog_chunks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS catalog_parents_v2 (LIKE catalog_parents INCLUDING ALL);

GRANT SELECT ON catalog_chunks_v2, catalog_parents_v2 TO "sg-agent@storegear-prod-ag26.iam";
GRANT SELECT, INSERT, UPDATE, DELETE ON catalog_chunks_v2, catalog_parents_v2 TO "sg-ingestion@storegear-prod-ag26.iam";
GRANT SELECT ON catalog_chunks_v2, catalog_parents_v2 TO "{{ADMIN_EMAIL}}";
