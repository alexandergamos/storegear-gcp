"""Prove least privilege on the catalog: connect AS each identity (IAM database auth, no passwords).

    uv run python infra/sql/check_access.py

- Alexander connects with his own login (ADC).
- sg-agent and sg-ingestion are reached by *impersonation* (Service Account Token Creator, ADR-002),
  so the test runs with exactly their permissions.
Expected: everyone can read; only sg-ingestion can write; sg-agent's write is refused.
"""
import os
import google.auth
from google.auth import impersonated_credentials
from google.cloud.sql.connector import Connector

PROJECT = "storegear-prod-ag26"
INSTANCE = f"{PROJECT}:europe-west1:sg-catalog"
SCOPES = ["https://www.googleapis.com/auth/sqlservice.login", "https://www.googleapis.com/auth/cloud-platform"]


def creds_for(sa: str | None):
    base, _ = google.auth.default(scopes=SCOPES)
    if sa is None:
        return base
    return impersonated_credentials.Credentials(source_credentials=base, target_principal=sa, target_scopes=SCOPES)


def check(label: str, db_user: str, sa: str | None) -> None:
    with Connector(credentials=creds_for(sa)) as connector:
        conn = connector.connect(INSTANCE, "pg8000", user=db_user, db="storegear", enable_iam_auth=True)
        cur = conn.cursor()
        cur.execute("SELECT current_user, count(*) FROM catalog_chunks")
        who, n = cur.fetchone()
        print(f"{label:13} read  OK   as {who} ({n} chunks)")
        try:
            cur.execute("INSERT INTO catalog_parents (parent_id, parent_context) VALUES ('__access_test__', 'x')")
            cur.execute("DELETE FROM catalog_parents WHERE parent_id = '__access_test__'")
            conn.rollback()
            print(f"{label:13} write OK   (rolled back)")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            print(f"{label:13} write DENIED ({str(e)[:60]})")
        conn.close()


if __name__ == "__main__":
    check("alexander", os.environ["STOREGEAR_ADMIN_EMAIL"], None)
    check("sg-agent", f"sg-agent@{PROJECT}.iam", f"sg-agent@{PROJECT}.iam.gserviceaccount.com")
    check("sg-ingestion", f"sg-ingestion@{PROJECT}.iam", f"sg-ingestion@{PROJECT}.iam.gserviceaccount.com")
