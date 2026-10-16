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
