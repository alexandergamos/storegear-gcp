# ADR-002 — Identity and secrets model

- **Status:** Accepted (2026-10-16)
- **Date:** 2026-10-16
- **Linear:** SMO-8
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Every running piece of the system (the agent, the ingestion job, later the CI pipeline) has to prove **who it is** to other Google services (Agent Platform, Cloud SQL, Drive, Sheets). It also needs a few **secrets** that aren't Google identities.

Key concepts:
- **IAM:** *who* (a principal) can do *what* (a role, which bundles permissions) on *which resource*.
- **Service account (SA):** an identity for software, not a person, with an email like `name@project.iam.gserviceaccount.com`.
- **Least privilege:** each identity gets only the roles it needs, on the narrowest resource possible. If it's compromised, the damage stays small.
- **Attached identity:** Cloud Run and Agent Engine run *as* a service account. Google hands it short-lived tokens automatically, so no key file exists anywhere.
- **Application Default Credentials (ADC):** the client libraries look for credentials in a fixed order (attached SA in the cloud, your own login on the laptop). The same code works in both places without changes.

In n8n, all of this was hidden in the credential manager: one credential per service, held by the platform.

## Options considered

### 1. Which identity runs our code
| Option | Pros | Cons |
|---|---|---|
| Default Compute service account | Zero setup | Historically holds **Editor** on the whole project. Any bug can do anything. Classic anti-pattern |
| One shared custom SA for everything | Simple | The agent could do whatever ingestion can (write the catalog, read Drive) |
| **One SA per component** | Least privilege; clear audit trail per component | More SAs and grants to manage |

### 2. How credentials reach the code
| Option | Pros | Cons |
|---|---|---|
| SA JSON key files | Works everywhere | Long-lived secrets on disk that leak through git, laptops and logs. Google recommends against them; many organisations block them |
| **Attached SA in the cloud + ADC on the laptop** | No keys at all; short-lived tokens | Local tests run with *your* permissions unless you impersonate the SA |
| Workload Identity Federation (for GitHub CI) | No keys for external CI | Only needed in Phase 4 (SMO-28) |

### 3. Database authentication (Cloud SQL Postgres, SMO-10)
| Option | Pros | Cons |
|---|---|---|
| Username + password in Secret Manager | Familiar; works with every driver | A secret to rotate and protect |
| **IAM database authentication** | The SA *is* the DB user; no password exists | Needs the Cloud SQL Python Connector (fine for us) and a DB grant per SA |

## Decision
**Service accounts**, one per component, created now (CI comes in SMO-28):

| SA | Used by | Roles (project level unless noted) |
|---|---|---|
| `sg-agent` | the ADK agent runtime | Agent Platform User (`roles/aiplatform.user`) · Cloud SQL Client · Cloud SQL Instance User · Logs Writer · Monitoring Metric Writer · Cloud Trace Agent · Secret Accessor **on specific secrets only** |
| `sg-ingestion` | the ingestion job | Agent Platform User (`roles/aiplatform.user`) · Cloud SQL Client · Cloud SQL Instance User · Logs Writer · (Document AI API User in Phase 2) |

- **Drive and Sheets:** not IAM roles. The SA email is **shared on the Drive folder or Sheet** like a colleague would be: Viewer only. Access is limited to exactly those files.
- **No JSON keys, ever.** Locally: `gcloud auth application-default login`. To test with exactly the SA's permissions: **impersonation**, which needs `Service Account Token Creator` for Alexander on each SA.
- **Database:** IAM database authentication, so there's no DB password.
- **Secret Manager** only for what isn't a Google identity: the JWT signing secret (Phase 3) and any third-party key. Regional replication in `europe-west1`. Access is granted per secret, not project-wide.
- **Humans:** Alexander keeps Owner for setup. Runtime never uses his identity.

## Consequences
- **Good:** no secrets on disk; a leaked repo or laptop exposes no credentials; each component can do only its own job.
- **Bad / accepted:** more grants to manage. Local runs use Alexander's broad permissions unless impersonating, so "works on my machine" can hide a missing role. Always do a final test with impersonation.
- **Caveats:** IAM changes can take a minute or two to propagate. "Cloud SQL Instance User" is the role for IAM DB login, and "Cloud SQL Client" is the role to connect; both are needed. Sharing a Drive folder with an SA works only for the files inside it.

## Revisit when
- CI arrives (SMO-28): add `sg-deploy` with Workload Identity Federation.
- Multiple environments arrive: one set of SAs per project.

## Learn more
- Service accounts best practices: https://cloud.google.com/iam/docs/best-practices-service-accounts
- Application Default Credentials: https://cloud.google.com/docs/authentication/application-default-credentials
- Cloud SQL IAM database authentication: https://cloud.google.com/sql/docs/postgres/iam-authentication
- Secret Manager best practices: https://cloud.google.com/secret-manager/docs/best-practices
