-- 007_swap_catalog_v3.sql · SMO-20 · make the catalog rebuilt by the Google pipeline (_v3) live (ADR-012)
-- One transaction (apply.py commits at the end): the agent never sees half a swap. Grants travel with the tables.
-- The queue rows move with the tables: the _v3 jobs become the live history (so the 15-minute sync sees every file as
-- already ingested), and the old live rows follow the old tables to _v2.
-- Rollback: the same renames and target updates in reverse.
--   uv run python infra/sql/apply.py infra/sql/007_swap_catalog_v3.sql

ALTER TABLE catalog_chunks RENAME TO catalog_chunks_v2;
ALTER TABLE catalog_parents RENAME TO catalog_parents_v2;
ALTER TABLE catalog_chunks_v3 RENAME TO catalog_chunks;
ALTER TABLE catalog_parents_v3 RENAME TO catalog_parents;
UPDATE ingest_queue SET target = '_v2' WHERE target = '';
UPDATE ingest_queue SET target = '' WHERE target = '_v3';
