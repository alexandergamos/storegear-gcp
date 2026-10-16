# StoreGear on Google Cloud — Build Log / Diario de construcción

Bilingual diary (EN + ES), one entry per Linear issue. It feeds the thesis annex.

| # | Date | Issue | Title |
|---|---|---|---|
| 1 | 2026-10-15 | SMO-6 | Repo, ADR process and project docs |
| 2 | 2026-10-16 | SMO-7 | Google Cloud project, budget and APIs |

---

## 1 · Repo, ADR process and project docs (SMO-6) — 2026-10-15

### EN
- **What:** created the `storegear-gcp` repo with a monorepo layout (`agent/`, `ingestion/`, `eval/`, `infra/`, `docs/`), an ADR template, `CLAUDE.md` working rules and ADR-000 (scope and success criteria).
- **Why:** in n8n, the "why" lived in the backlog and the build log. In a code-first product, the decisions sit next to the code (ADRs), so the trail travels with the repo.
- **Learned:** an ADR records *one* decision with its context and trade-offs. It is never edited afterwards; a new ADR supersedes it.
- **Next:** SMO-7, the Google Cloud project, budget and APIs.

### ES
- **Qué:** creado el repo `storegear-gcp` con estructura monorepo (`agent/`, `ingestion/`, `eval/`, `infra/`, `docs/`), plantilla de ADR, reglas de trabajo en `CLAUDE.md` y el ADR-000 (alcance y criterios de éxito).
- **Por qué:** en n8n el "por qué" vivía en el backlog y el diario. En un producto basado en código, las decisiones viven junto al código (ADRs), así que el historial viaja con el repo.
- **Aprendido:** un ADR recoge *una* decisión con su contexto y sus trade-offs. No se edita después; se sustituye con un ADR nuevo.
- **Siguiente:** SMO-7, proyecto de Google Cloud, presupuesto y APIs.

---

## 2 · Google Cloud project, budget and APIs (SMO-7) — 2026-10-16

### EN
- **What:** project `storegear-prod-ag26` created in the Console and billing linked (no free credits). Budget of €30 a month with alerts and an enforced spend cap. The six APIs for Phases 0–1 are enabled. ADR-001 fixes the region (`europe-west1`), the one-project layout and the cost guardrails. `infra/runbook.md` records every Console step with its `gcloud` equivalent.
- **Why:** a project has no region, so the region is a team rule applied to each resource. A cap protects a learning project from a runaway loop.
- **Learned:** budgets used to be alerts only; Google now offers enforced spend caps that pause services. New projects come with ~50 APIs already enabled. "ClickOps" is fine for learning if every click is written down as code.
- **Next:** SMO-8, service accounts, least privilege and Secret Manager.

### ES
- **Qué:** creado el proyecto `storegear-prod-ag26` desde la consola y vinculada la facturación (sin créditos gratuitos). Presupuesto de 30 € al mes con alertas y un límite de gasto forzado. Activadas las seis APIs de las fases 0 y 1. El ADR-001 fija la región (`europe-west1`), un único proyecto y las protecciones de coste. `infra/runbook.md` recoge cada paso de la consola con su equivalente en `gcloud`.
- **Por qué:** un proyecto no tiene región, así que la región es una regla de equipo que se aplica a cada recurso. El límite protege un proyecto de aprendizaje frente a un bucle descontrolado.
- **Aprendido:** antes los presupuestos solo avisaban; ahora Google ofrece límites de gasto que pausan los servicios. Un proyecto nuevo trae unas 50 APIs ya activadas. Hacer "ClickOps" está bien para aprender si cada clic queda escrito como código.
- **Siguiente:** SMO-8, cuentas de servicio, mínimo privilegio y Secret Manager.

---
