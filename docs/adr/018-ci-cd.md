# ADR-018 — CI/CD: GitHub Actions with keyless deploys, and the eval as a release gate

- **Status:** Accepted (2026-10-24, Alexander: option A)
- **Date:** 2026-10-24
- **Linear:** SMO-28
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
Today every change reaches Google Cloud by hand: `gcloud builds submit` with `api/cloudbuild.yaml`, then `gcloud run deploy`, following `infra/runbook.md`. Tests run only on the laptop. The master's rubric asks for monitoring and CI/CD for the top grades, and the threat model (E4) lists "CI/CD with the eval as a gate" as the control for unreviewed changes reaching production.

Constraints:
- **No service-account keys, ever** (CLAUDE.md). External CI must use Workload Identity Federation (ADR-002 already planned an `sg-deploy` account for this).
- **Alexander runs infrastructure steps** (IAM, pools, triggers); the pipeline files are code and live in the repo.
- **The eval costs money and is noisy:** one run scored 4.64 and the next 5.00 with no code change (ADR-015). A gate that blocks on a single run would block good releases.
- **Leftover from ADR-014:** the default Compute account still holds Editor because Cloud Build used it. CI must bring its own build account so Editor can go.
- **Image size:** the `sg-api` image installs the whole project (ADK, Document AI, numpy, pypdf…) although the API uses a fraction of it: ~126 MB compressed. A smaller image starts faster on a cold start (25 s measured).

n8n has no CI: changes are made in the editor and a nightly workflow backs them up to git. That is fine for a no-code tool, and it is exactly the gap this build is meant to show.

## Options considered
| Option | Pros | Cons | Cost (rough) |
|---|---|---|---|
| **A. GitHub Actions + Workload Identity Federation (recommended)** | Checks run on every push and pull request, visible in GitHub next to the code (what a reviewer or the jury sees); keyless deploys with a short-lived token scoped to this repo; the industry-standard pattern | One-time setup: identity pool, provider, `sg-deploy` account and its roles; two places to look at logs (GitHub for tests, Cloud Build for the image) | Free (private repo: 2,000 Actions minutes/month; Cloud Build first 120 min/day free) |
| B. Cloud Build triggers connected to GitHub | Everything stays inside Google Cloud, one IAM model, no federation | The GitHub connection is set up in the console; results are less visible from the repo; tests and deploy in one YAML that is harder to run locally | Free within Cloud Build's daily allowance |
| C. GitHub Actions for tests only; deploys stay manual | No cloud access from CI at all, nothing to federate | Doesn't remove the manual path to production, the risk E4 names; Editor can't be removed from the default account | Free |

## Decision
**A**, in four workflows (`.github/workflows/`):

1. **`ci.yml`, on every push and pull request** (no cloud credentials): `uv sync`, then the unit tests of `api/`, `infra/` and `eval/` with fakes. A red test blocks the merge.
2. **`deploy-api.yml`, on push to `main` when `api/`, the prompt or the dependencies change:** the same tests → keyless login as `sg-deploy` → build the image **on the GitHub runner** and push it to Artifact Registry → deploy a new `sg-api` revision **with no traffic**, tagged `candidate` → smoke checks against the candidate URL (`/health`, `/status`, `/catalog/models`, 401 on `/chat` and `/compare` without a login) → move 100 % of traffic. If a check fails, the old revision keeps serving. The role checks (403, staff vs manager) need test passwords, so they stay in `eval/auth_tests.py`, run by hand, instead of becoming GitHub secrets.
3. **`eval-gate.yml`, by hand (workflow_dispatch) and before any agent or prompt release**, from `main` only (GitHub environment `eval`; required reviewers aren't available on a private repo on this plan, so the control is that only Alexander, the sole collaborator, can start it): the 22-question eval of the deployed agent, as `sg-agent` (the identity the eval uses on the laptop). **Pass rule** (`eval/gate.py`): every metric ≥ baseline − 0.1 and no availability error left. Questions whose answer is an availability error (`ERROR …` from `run_eval.py`) run once more before scoring; a wrong answer is never retried. The result JSON is attached to the run.
4. **`retention.yml`, weekly:** the 30-day audit (ADR-016) as `sg-ops`, an account limited to Agent Sessions.

Alongside:
- **A slimmer `sg-api` image:** dependencies split into two groups, `api` (what `api/*.py` imports) and `workers` (agent, ingestion, eval, infra). The API image installs `api` only; the laptop and CI install both, as before. The 96 API tests pass with the `api` group alone.
- **Each GitHub environment can become one account only** (`production` → `sg-deploy`, `eval` → `sg-agent`, `ops` → `sg-ops`), and the federation trusts tokens from this repository only.
- **Editor on the default Compute account** stays until the ingestion worker image also builds in CI: it is still built with `gcloud builds submit`, which uses that account.

## Consequences
- **Good:** no change to sg-api reaches production without passing tests and smoke checks; deploys are repeatable and logged; no keys exist anywhere; the jury sees green checks on the repo.
- **Bad / accepted trade-offs:** the eval gate is manual (it costs about $0.25 per run and a single run is noisy), so prompt quality relies on running it before a release; federation adds IAM to understand; the agent itself (Agent Runtime) still deploys with `infra/deploy_agent_runtime.py` by hand; the Editor leftover stays open for now.
- **GitHub plan:** environment branch policies work (`production` and `eval` accept `main` only); required reviewers don't on a private repo without GitHub Pro/Team. They become free if the repository goes public.
- **Caveats and gotchas:** the federation provider must restrict tokens to this repository (`attribute.repository`) and, for deploys, to `main`, or any fork could deploy; the `candidate` tag URL is public like the service itself (it still requires a login); Cloud Run keeps the last revisions, so rollback is `gcloud run services update-traffic`.

## Revisit when
- Another person deploys: add branch protection with required reviews and move the eval gate to every pull request that touches the agent.
- Terraform arrives (ADR-001): the pool, provider and accounts move into code.
- The eval becomes cheap and stable enough (a reranker, cached judges) to run on every merge.

## Learn more
- Workload Identity Federation with GitHub Actions: https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- `google-github-actions/auth`: https://github.com/google-github-actions/auth
- Cloud Run gradual rollouts and tags: https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration
- uv dependency groups: https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups
