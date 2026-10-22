-- 009_web_demo.sql · SMO-35 · sg-api for the web demo (ADR-017)
--   uv run python infra/sql/apply.py infra/sql/009_web_demo.sql

-- GET /catalog/models: model names from the staff manuals (file names only, never chunk text to the client)
GRANT SELECT ON catalog_chunks TO "sg-api@storegear-prod-ag26.iam";
