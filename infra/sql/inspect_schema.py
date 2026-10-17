"""Quick read-only look at the catalog schema (as the postgres admin).

    uv run python infra/sql/inspect_schema.py
"""
from google.cloud import secretmanager
from google.cloud.sql.connector import Connector

PROJECT = "storegear-prod-ag26"
pw = secretmanager.SecretManagerServiceClient().access_secret_version(
    name=f"projects/{PROJECT}/secrets/sg-db-postgres-password/versions/latest").payload.data.decode()

with Connector() as c:
    conn = c.connect(f"{PROJECT}:europe-west1:sg-catalog", "pg8000", user="postgres", password=pw, db="storegear")
    cur = conn.cursor()
    cur.execute("SELECT version()")
    print(cur.fetchone()[0][:40])
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    print("pgvector", cur.fetchone()[0])
    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'catalog_%' ORDER BY 1")
    print("indexes:", ", ".join(r[0] for r in cur.fetchall()))
    cur.execute("SELECT to_tsvector('spanish', 'Las baterías del reloj resisten el agua')::text")
    print("spanish FTS example:", cur.fetchone()[0])
    conn.close()
