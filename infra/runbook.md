# Infra runbook

Every change made in the Cloud Console is recorded here with its `gcloud` equivalent, so the project can be rebuilt from this file (until Terraform replaces it, SMO-30). Region for everything: **`europe-west1`** (ADR-001).

```bash
PROJECT_ID=storegear-prod-ag26
REGION=europe-west1
```

## Local gcloud configuration (one-time)
A named configuration keeps StoreGear separate from other projects on this laptop. The `default` configuration points at `claude-code-gws-505419` (the AIOS Google Workspace CLI project); don't change it.
```bash
gcloud config configurations create storegear
gcloud config set account <admin-email>
gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set run/region $REGION
gcloud config configurations activate default   # switch back when done
```
Use `gcloud config configurations activate storegear` to work on this project, or pass `--project $PROJECT_ID` on each command.

## SMO-7 · Project, billing, budget, APIs (2026-10-16, done in the Console)

**1. Project**
```bash
gcloud projects create $PROJECT_ID --name="StoreGear"
```

**2. Billing**
```bash
gcloud billing accounts list
gcloud billing projects link $PROJECT_ID --billing-account=<BILLING_ACCOUNT_ID>
gcloud billing projects describe $PROJECT_ID   # billingEnabled: true
```

**3. Budget (€30/month, alerts 50/90/100 % + 100 % forecast) and spend cap**
```bash
gcloud billing budgets create --billing-account=<BILLING_ACCOUNT_ID> \
  --display-name="storegear-monthly" --budget-amount=30EUR \
  --filter-projects=projects/$PROJECT_ID \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 --threshold-rule=percent=1.0,basis=forecasted-spend
```
The enforced spend cap is set in the Console (Billing → Budgets & caps). Check `gcloud billing budgets --help` for cap flags before scripting it; this feature is new.

**4. APIs**
```bash
gcloud services enable aiplatform.googleapis.com secretmanager.googleapis.com \
  sqladmin.googleapis.com run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com --project $PROJECT_ID
gcloud services list --enabled --project $PROJECT_ID
```
Later phases add `documentai.googleapis.com` (Phase 2), `cloudscheduler.googleapis.com`, and `drive.googleapis.com` / `sheets.googleapis.com` for the tools.

## SMO-8 · Service accounts and IAM (2026-10-16, Console; ADR-002)

**1. Service accounts**
```bash
gcloud iam service-accounts create sg-agent --display-name="StoreGear agent runtime" --project $PROJECT_ID
gcloud iam service-accounts create sg-ingestion --display-name="StoreGear ingestion job" --project $PROJECT_ID
```

**2. Project roles** (no Owner or Editor, ever)
```bash
for R in aiplatform.user cloudsql.client cloudsql.instanceUser logging.logWriter monitoring.metricWriter cloudtrace.agent; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:sg-agent@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/$R" --condition=None
done
for R in aiplatform.user cloudsql.client cloudsql.instanceUser logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:sg-ingestion@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/$R" --condition=None
done
```
Secret access is granted per secret when each secret is created, never at project level:
```bash
gcloud secrets add-iam-policy-binding <SECRET> --member="serviceAccount:sg-agent@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

**3. Let Alexander impersonate the SAs** (to test with exactly their permissions)
```bash
for SA in sg-agent sg-ingestion; do
  gcloud iam service-accounts add-iam-policy-binding $SA@$PROJECT_ID.iam.gserviceaccount.com \
    --member="user:<admin-email>" --role="roles/iam.serviceAccountTokenCreator"
done
```

**4. Local credentials** (ADC; no key files)
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project $PROJECT_ID
```

## SMO-10 · Cloud SQL Postgres + pgvector (2026-10-16, Console; ADR-004)

**1. Admin password → Secret Manager** (generated in the Console; never in chat or files)
```bash
gcloud secrets create sg-db-postgres-password --replication-policy=user-managed --locations=$REGION
printf '%s' "<PASTE>" | gcloud secrets versions add sg-db-postgres-password --data-file=-
```

**2. Instance**
```bash
gcloud sql instances create sg-catalog --database-version=POSTGRES_17 --edition=ENTERPRISE \
  --tier=db-f1-micro --region=$REGION --availability-type=ZONAL \
  --storage-type=SSD --storage-size=10 --storage-auto-increase \
  --backup --backup-start-time=02:00 --retained-backups-count=7 \
  --assign-ip --authorized-networks="" --deletion-protection \
  --database-flags=cloudsql.iam_authentication=on \
  --root-password="$(gcloud secrets versions access latest --secret=sg-db-postgres-password)"
gcloud sql databases create storegear --instance=sg-catalog
```

**3. IAM database users** (no passwords; ADR-002)
```bash
gcloud sql users create sg-agent@$PROJECT_ID.iam --instance=sg-catalog --type=cloud_iam_service_account
gcloud sql users create sg-ingestion@$PROJECT_ID.iam --instance=sg-catalog --type=cloud_iam_service_account
gcloud sql users create <admin-email> --instance=sg-catalog --type=cloud_iam_user
```

**4. Stop / start** (cost lever: stopped = storage only)
```bash
gcloud sql instances patch sg-catalog --activation-policy=NEVER    # stop
gcloud sql instances patch sg-catalog --activation-policy=ALWAYS   # start
```

**5. Schema** (code, not Console: `infra/sql/`)
```bash
uv run python infra/sql/apply.py infra/sql/001_schema.sql   # as postgres; password read from Secret Manager, never printed
uv run python infra/sql/inspect_schema.py                   # versions, indexes, Spanish FTS sample
uv run python infra/sql/check_access.py                     # least-privilege proof via impersonation
```
Expected access: everyone reads; only `sg-ingestion` writes; `sg-agent` and Alexander get "permission denied" on writes.

## SMO-11 · Catalog load (2026-10-17; ADR-005)
Inputs: `data/catalog_chunks.csv`, `data/catalog_parents.csv` (exported from n8n's Supabase Table Editor; git-ignored).
```bash
uv run python ingestion/embed_export.py gemini-embedding-2       # ~5 min, one text per call (eu endpoint)
uv run python eval/retrieval_benchmark.py gemini-embedding-2     # manual@1 / manual@5 / MRR on 17 questions
uv run python ingestion/load_catalog.py gemini-embedding-2       # as sg-ingestion (impersonation); idempotent upsert
```

## SMO-12 · Hybrid search benchmark (2026-10-17)
```powershell
$env:STOREGEAR_IMPERSONATE_SA="sg-agent@storegear-prod-ag26.iam.gserviceaccount.com"   # run AS the agent
uv run python eval/hybrid_benchmark.py
```

## SMO-13 · Agent prerequisites (2026-10-17, Console)
- Enable **Google Sheets API**: `gcloud services enable sheets.googleapis.com --project $PROJECT_ID`
- Share the **StoreGear** sheet (`1KnKC0iFDCzChg9szTkDazkwmgqQGQpbDg2raZ0EI2m4`) with `sg-agent@$PROJECT_ID.iam.gserviceaccount.com` as **Viewer** (Drive sharing, not IAM).
- Try the agent: `copy agent/storegear/.env.example agent/storegear/.env`, then `uv run python agent/ask.py "pregunta"` or `cd agent; uv run adk web`.

## SMO-14 · Eval gate (2026-10-17; ADR-007)
```bash
uv run python eval/run_eval.py              # 22 questions, ~10 min, a few cents; results in eval/results/ (git-ignored)
uv run python eval/run_eval.py --only 6 13  # subset while iterating
```
Gate: every metric ≥ n8n baseline − 0.1 (Corr 4.90 · Faith 4.85 · Ctx 4.90 · Ans 4.90).

## SMO-15 · Agent Runtime deploy (2026-10-18; ADR-008)
Prerequisites (Console, project **StoreGear** selected in the top bar):
- Bucket `storegear-prod-ag26-agent-staging` (multi-region EU, uniform access) **in the StoreGear project**; `sg-agent` = Storage Object Viewer on it.
- `sg-agent` = **Service Account Token Creator on itself** (scoped token for the Sheets API inside the runtime):
  `gcloud iam service-accounts add-iam-policy-binding sg-agent@$PROJECT_ID.iam.gserviceaccount.com --member="serviceAccount:sg-agent@$PROJECT_ID.iam.gserviceaccount.com" --role=roles/iam.serviceAccountTokenCreator`
```bash
uv run python infra/deploy_agent_runtime.py            # first time
uv run python infra/deploy_agent_runtime.py --update   # later (same resource, infra/agent_runtime.json)
uv run python infra/ask_remote.py "pregunta"           # test the deployed agent
```

## SMO-16 · Document AI (2026-10-18, Console; ADR-009)
```bash
gcloud services enable documentai.googleapis.com --project $PROJECT_ID
# Processor: Console → Document AI → Processor gallery → Layout Parser → name sg-layout-parser, region eu
# ID: 8a9ba69484bf2664 · endpoint https://eu-documentai.googleapis.com
uv run python ingestion/parser_test.py gemini
uv run python ingestion/parser_test.py docai --processor 8a9ba69484bf2664
```

## SMO-17 · New catalog: parse, chunk, load, swap (2026-10-18; ADR-009 addendum)
```bash
uv run python ingestion/parse_manuals.py                    # data/parsed/full/*.md + report.json (resumable)
uv run python ingestion/chunk_manuals.py                    # data/catalog_v2/{chunks,parents}.csv
uv run python infra/sql/apply.py infra/sql/002_catalog_v2.sql   # side tables catalog_*_v2 + grants
uv run python ingestion/embed_export.py gemini-embedding-2 data/catalog_v2/chunks.csv
uv run python ingestion/load_catalog.py gemini-embedding-2 --v2
STOREGEAR_CATALOG_SUFFIX=_v2 uv run python eval/hybrid_benchmark.py   # benchmark + eval against v2 before going live
STOREGEAR_CATALOG_SUFFIX=_v2 uv run python eval/run_eval.py
uv run python infra/sql/apply.py infra/sql/003_swap_catalog_v2.sql    # one transaction; v1 kept as catalog_*_v1
# Rollback: the same four renames in reverse (live -> _v2, _v1 -> live).
```

## SMO-18 · Injection gate (2026-10-19; ADR-010)
```bash
# Console: enable Model Armor API; template sg-ingestion-pi (eu, PI + jailbreak only, low and above) kept for Phase 3/4
uv run python infra/sql/apply.py infra/sql/004_quarantine.sql
uv run python eval/injection_benchmark.py build && uv run python eval/injection_benchmark.py run regex gemini armor
PYTHONPATH=ingestion uv run python ingestion/check_catalog.py            # after chunk_manuals, before embed/load
PYTHONPATH=ingestion uv run python ingestion/check_catalog.py --apply    # record flags + remove them from the live catalog
# Review (as Alexander): UPDATE catalog_quarantine SET status='approved', reviewed_at=now() WHERE parent_id='...';
```

## SMO-19 · Ingestion queue + Cloud Run job (2026-10-20; ADR-011)
```bash
uv run python infra/sql/apply.py infra/sql/005_ingest_queue.sql
uv run python ingestion/enqueue.py "Interno"                      # local test: enqueue (twice = no-op)
STOREGEAR_LOCAL_PDFS=1 uv run python ingestion/worker.py          # local test: drain the queue
# Console (done by Alexander):
#  APIs: Cloud Run Admin, Artifact Registry, Cloud Build, Google Drive
#  Artifact Registry: Docker repo "storegear", multi-region europe (EU)
#  IAM for sg-ingestion: Agent Platform User (roles/aiplatform.user), Document AI API User, Logs Writer; Token Creator on itself (Drive scope)
#  Drive: share the manuals folder with sg-ingestion@storegear-prod-ag26.iam.gserviceaccount.com (Viewer)
gcloud meta list-files-for-upload                                  # check: only code + lock file
gcloud builds submit --tag europe-docker.pkg.dev/storegear-prod-ag26/storegear/ingest-worker:v1
#  Cloud Run > Jobs > Create: sg-ingest-worker, europe-west1, that image, SA sg-ingestion, 2 CPU / 2 GiB,
#  task timeout 3600 s, max retries 0 (the queue retries), 1 task
#  Logging > Logs Explorer: jsonPayload.message="INGEST_DEAD" > Create alert > email channel
```
# Lessons (2026-10-20): enable the Google Drive API in the project (first cloud run got 403 "API not used in project");
# grant Token Creator ON the service account itself, never at project level; then verify:
#   gcloud projects get-iam-policy storegear-prod-ag26 --flatten="bindings[].members" --filter="bindings.role:serviceAccountTokenCreator"
#   gcloud iam service-accounts add-iam-policy-binding <sa> --member=serviceAccount:<sa> --role=roles/iam.serviceAccountTokenCreator

## SMO-20 · Drive sync + rebuild (2026-10-21; ADR-012)
```bash
uv run python infra/sql/apply.py infra/sql/006_sync_and_v3.sql
gcloud builds submit --tag europe-docker.pkg.dev/storegear-prod-ag26/storegear/ingest-worker:v2
#  Console: job image -> v2; Execute with overrides: 3 tasks, env STOREGEAR_CATALOG_SUFFIX=_v3 (rows enqueued by sync.run(conn,'_v3',rebuild=True))
STOREGEAR_CATALOG_SUFFIX=_v3 uv run --env-file agent/storegear/.env python eval/hybrid_benchmark.py
STOREGEAR_CATALOG_SUFFIX=_v3 uv run python eval/run_eval.py
uv run python infra/sql/apply.py infra/sql/007_swap_catalog_v3.sql   # one transaction; old catalog kept as catalog_*_v2
#  Job default argument --sync; Cloud Run Invoker ON the job for sg-ingestion:
gcloud run jobs add-iam-policy-binding sg-ingest-worker --region europe-west1 --member=serviceAccount:sg-ingestion@storegear-prod-ag26.iam.gserviceaccount.com --role=roles/run.invoker
gcloud scheduler jobs create http sg-ingest-sync --location europe-west1 --schedule="*/15 * * * *" --time-zone="Europe/Madrid" --http-method=POST --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/storegear-prod-ag26/jobs/sg-ingest-worker:run" --oauth-service-account-email=sg-ingestion@storegear-prod-ag26.iam.gserviceaccount.com
# Cloud Scheduler needed ~1 h 45 min after enabling the API before it dispatched anything.
# Job command (args REPLACE the image CMD; from PowerShell, quote the comma list):
#   gcloud run jobs update sg-ingest-worker --region europe-west1 --command=/app/.venv/bin/python "--args=ingestion/worker.py,--sync"
```

## SMO-22 · Login and roles (2026-10-21; ADR-014)
```bash
#  Console: Identity Platform enabled (direct link: marketplace .../customer-identity), provider Email/Password only,
#  Settings > Users: sign-up OFF; API key restricted to Identity Toolkit API + Token Service API;
#  service account sg-api (Agent Platform User, Cloud SQL Client, Cloud SQL Instance User, Logs Writer) + IAM DB user
uv run python infra/sql/apply.py infra/sql/008_api_rate.sql
uv run python infra/users.py test-users                     # writes test credentials to agent/storegear/.env
gcloud builds submit --config api/cloudbuild.yaml --substitutions=_TAG=v2
gcloud run deploy sg-api --image europe-docker.pkg.dev/storegear-prod-ag26/storegear/sg-api:v2 --region europe-west1
#  first deploy in the Console: public access, SA sg-api, max 2 instances, concurrency 10, timeout 300 s, 1 CPU / 1 GiB
uv run --env-file agent/storegear/.env python eval/auth_tests.py   # 7/7
```

## SMO-23 · Guardrails + PII (2026-10-21; ADR-015)
```bash
#  Console: Model Armor template sg-guard (multi-region eu): PI+jailbreak medium+, 4 RAI filters medium+, malicious URLs on, SDP off
#  IAM: sg-api + Model Armor User
gcloud builds submit --config api/cloudbuild.yaml --substitutions=_TAG=v3
gcloud run deploy sg-api --image europe-docker.pkg.dev/storegear-prod-ag26/storegear/sg-api:v3 --region europe-west1
uv run python infra/deploy_agent_runtime.py --update          # explicit safety settings + file_id validation
uv run --env-file agent/storegear/.env python eval/guardrail_tests.py --eval   # 10/10
uv run python eval/run_eval.py --remote
```

## SMO-24 · Sessions + retention (2026-10-22; ADR-016)
```bash
gcloud builds submit --config api/cloudbuild.yaml --substitutions=_TAG=v4
gcloud run deploy sg-api --image europe-docker.pkg.dev/storegear-prod-ag26/storegear/sg-api:v4 --region europe-west1
uv run python infra/sessions_retention.py --dry-run && uv run python infra/sessions_retention.py   # audit, then enforce 30 d
uv run --env-file agent/storegear/.env python eval/session_tests.py      # 6/6
uv run python infra/deploy_agent_runtime.py --update                    # STOREGEAR_RETURN_N=7
uv run python eval/run_eval.py --remote                                 # mirrors the deployed RETURN_N; run twice
```

## SMO-35 · Web demo API (2026-10-22; ADR-017)
```bash
#  Alexander, Console: Secret Manager > create n8n-jwt-secret (>= 32 random bytes, generated by Alexander, never pasted in chat);
#  the same value in the n8n credential "JWT Auth account 2"; IAM on THAT secret only: sg-api -> Secret Manager Secret Accessor
uv run python infra/sql/apply.py infra/sql/009_web_demo.sql             # column grant on catalog_chunks + compare tables
#  after any catalog swap by rename (as in 003/007), re-run the catalog_chunks GRANT line of 009, or /catalog/models fails
uv run pytest api/tests infra/tests -q                                  # all pass, fakes only
gcloud builds submit --config api/cloudbuild.yaml --substitutions=_TAG=v5
gcloud run deploy sg-api --image europe-docker.pkg.dev/storegear-prod-ag26/storegear/sg-api:v5 --region europe-west1 \
  --set-secrets STOREGEAR_N8N_JWT_SECRET=n8n-jwt-secret:latest \
  --update-env-vars "^@^STOREGEAR_ALLOWED_ORIGINS=<Firebase Hosting origins, comma-separated>"
uv run python infra/users.py test-users                                 # adds test-demo@storegear-gcp.test (staff + demo)
uv run --env-file agent/storegear/.env python eval/compare_tests.py     # n8n answers; Google slot errors while restricted
uv run --env-file agent/storegear/.env python eval/auth_tests.py        # regression 7/7
uv run --env-file agent/storegear/.env python eval/session_tests.py     # regression 6/6 (needs Agent Platform)
#  jury accounts: uv run python infra/users.py add <email> staff --demo
#  after Agent Platform access returns: guardrail_tests.py --eval; then optionally STOREGEAR_PARTIAL_EVENTS=1 (check steps live)
```
**Vote retention:** once the SMO-29 report is written, export the vote summary, then in Cloud SQL Studio:
`DELETE FROM compare_votes; DELETE FROM compare_conversations;` (votes are tied to a uid; ADR-017).

## SMO-28 · CI/CD with keyless deploys (2026-10-24; ADR-018)
Alexander runs these once, in order. They create the GitHub federation, two new narrow accounts and their roles. No key is created at any step.

```bash
PROJECT=storegear-prod-ag26
PN=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
REPO=alexandergamos/storegear-gcp
POOL=projects/$PN/locations/global/workloadIdentityPools/github

# 1. The federation: GitHub's OIDC tokens are trusted only when they come from this repository
gcloud iam workload-identity-pools create github --project=$PROJECT --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc storegear-gcp --project=$PROJECT --location=global \
  --workload-identity-pool=github --display-name="storegear-gcp repo" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.repository == '$REPO'"

# 2. sg-deploy: pushes sg-api images and deploys sg-api revisions, nothing else
gcloud iam service-accounts create sg-deploy --project=$PROJECT --display-name="CI deploys of sg-api (GitHub Actions)"
gcloud artifacts repositories add-iam-policy-binding storegear --project=$PROJECT --location=europe \
  --member=serviceAccount:sg-deploy@$PROJECT.iam.gserviceaccount.com --role=roles/artifactregistry.writer
gcloud run services add-iam-policy-binding sg-api --project=$PROJECT --region=europe-west1 \
  --member=serviceAccount:sg-deploy@$PROJECT.iam.gserviceaccount.com --role=roles/run.developer
gcloud iam service-accounts add-iam-policy-binding sg-api@$PROJECT.iam.gserviceaccount.com --project=$PROJECT \
  --member=serviceAccount:sg-deploy@$PROJECT.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser

# 3. sg-ops: the weekly retention audit; Agent Sessions only
gcloud iam service-accounts create sg-ops --project=$PROJECT --display-name="Weekly retention audit (GitHub Actions)"
gcloud projects add-iam-policy-binding $PROJECT \
  --member=serviceAccount:sg-ops@$PROJECT.iam.gserviceaccount.com --role=roles/aiplatform.user

# 4. Who may become each account: one GitHub environment each (the job's "environment:" line).
#    This repo sends GitHub's *immutable* subject (owner and repo with their numeric ids), so the principal is
#    repo:alexandergamos@330485277/storegear-gcp@1420440664:environment:<env>. Check yours with:
#    gh api repos/$REPO/actions/oidc/customization/sub   (sub_claim_prefix). The plain repo:$REPO form is never sent.
SUBJECT="repo:alexandergamos@330485277/storegear-gcp@1420440664"
gcloud iam service-accounts add-iam-policy-binding sg-deploy@$PROJECT.iam.gserviceaccount.com --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser --member="principal://iam.googleapis.com/$POOL/subject/$SUBJECT:environment:production"
gcloud iam service-accounts add-iam-policy-binding sg-agent@$PROJECT.iam.gserviceaccount.com --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser --member="principal://iam.googleapis.com/$POOL/subject/$SUBJECT:environment:eval"
gcloud iam service-accounts add-iam-policy-binding sg-ops@$PROJECT.iam.gserviceaccount.com --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser --member="principal://iam.googleapis.com/$POOL/subject/$SUBJECT:environment:ops"

# 5. The value GitHub needs (repository variable GCP_WIF_PROVIDER)
echo "$POOL/providers/storegear-gcp"
```

**On GitHub** (done 2026-10-24 with `gh`):
- **Environments:** `production` and `eval` accept deployments from `main` only; `ops` has no rule. Required reviewers on `eval` aren't available on a private repo on this plan (HTTP 422): only Alexander, the sole collaborator, can start it.
- **Repository variable:** `GCP_WIF_PROVIDER` = `projects/1066603052728/locations/global/workloadIdentityPools/github/providers/storegear-gcp` (the value step 5 prints).
- **Variables of the `eval` environment:** `GOOGLE_CLOUD_LOCATION`, `STOREGEAR_MODEL`, `STOREGEAR_THINKING`, copied from `agent/storegear/.env` (none of them is a secret).

**Checks:** a push to any branch runs `ci`; merging to `main` runs `deploy sg-api` (the log prints the image size: v6 was ~126 MB compressed); Actions → `eval gate` → Run workflow asks for approval, then runs the 22 questions; Actions → `retention audit` → Run workflow.

**Later, not now:** the default Compute account keeps Editor until the ingestion worker image also builds in CI (it is still built with `gcloud builds submit`, which uses that account). Removing it earlier would break that build.

**First deploy (2026-10-24):** run 40093473026. The first attempt failed with `iam.serviceAccounts.getAccessToken` denied: the bindings used the plain `repo:OWNER/REPO` subject and GitHub sends the immutable one. After rebinding, revision `sg-api-00013-muk` passed all smoke checks and took 100 % of traffic. Image: **97 MB** compressed (v6: 126 MB, −23 %).
