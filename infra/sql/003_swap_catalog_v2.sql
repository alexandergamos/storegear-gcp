-- 003_swap_catalog_v2.sql · SMO-17 · make the re-parsed, table-aware catalog live (eval on v2: 4.95 / 5 / 5 / 5)
-- apply.py runs all statements in ONE transaction (committed at the end), so the agent never sees half a swap.
-- Grants travel with the tables. Rollback = the same renames in reverse (v1 back to the live names).
--   uv run python infra/sql/apply.py infra/sql/003_swap_catalog_v2.sql

ALTER TABLE catalog_chunks RENAME TO catalog_chunks_v1;
ALTER TABLE catalog_parents RENAME TO catalog_parents_v1;
ALTER TABLE catalog_chunks_v2 RENAME TO catalog_chunks;
ALTER TABLE catalog_parents_v2 RENAME TO catalog_parents;
