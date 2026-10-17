"""Apply a SQL file to the Cloud SQL catalog as the `postgres` admin.

    uv run python infra/sql/apply.py infra/sql/001_schema.sql

How it connects (ADR-002 / ADR-004):
- The Cloud SQL Python Connector opens an encrypted tunnel authorised by your Google login (ADC),
  so the instance needs no authorized networks.
- The admin password is read from Secret Manager at run time and never printed or written to disk.
"""
import sys

from google.cloud import secretmanager
from google.cloud.sql.connector import Connector

PROJECT = "storegear-prod-ag26"
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
DATABASE = "storegear"


def admin_password() -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT}/secrets/sg-db-postgres-password/versions/latest"
    return client.access_secret_version(name=name).payload.data.decode("utf-8")


def split_statements(sql: str) -> list[str]:
    """Split on ';' at line ends, ignoring comment lines. Enough for our DDL files (no functions/DO blocks)."""
    # drop whole-line comments and trailing "-- ..." comments (our DDL has no '--' inside strings)
    lines = [line.split("--", 1)[0].rstrip() for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";\n") if s.strip().strip(";")]


def main(path: str) -> None:
    sql = open(path, encoding="utf-8").read()
    with Connector() as connector:
        conn = connector.connect(INSTANCE, "pg8000", user="postgres", password=admin_password(), db=DATABASE)
        try:
            cur = conn.cursor()
            for stmt in split_statements(sql):
                cur.execute(stmt.rstrip(";"))
                print("ok  ", stmt.splitlines()[0][:90])
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    main(sys.argv[1])
