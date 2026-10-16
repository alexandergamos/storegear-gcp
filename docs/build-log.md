# StoreGear on Google Cloud — Build Log / Diario de construcción

Bilingual diary (EN + ES), one entry per Linear issue. It feeds the thesis annex.

| # | Date | Issue | Title |
|---|---|---|---|
| 1 | 2026-10-15 | SMO-6 | Repo, ADR process and project docs |
| 2 | 2026-10-16 | SMO-7 | Google Cloud project, budget and APIs |
| 3 | 2026-10-16 | SMO-8 | Service accounts, least privilege, no keys |
| 4 | 2026-10-16 | SMO-9 | Toolchain, ADK hello world, model endpoint decision |

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

## 3 · Service accounts, least privilege, no keys (SMO-8) — 2026-10-16

### EN
- **What:** two service accounts. `sg-agent` has 6 roles (Agent Platform user, Cloud SQL client + IAM DB user, logs, metrics, traces). `sg-ingestion` has 4. No JSON keys. Local Application Default Credentials. Alexander can impersonate both to test with exactly their permissions (tested: a token was issued). ADR-002 records the model, including IAM database authentication (no DB password).
- **Why:** in n8n, keys lived in a credential manager. In Google Cloud, the code gets an identity and Google issues short-lived tokens, so there's nothing to leak.
- **Learned:** the default compute service account comes with **Editor** on the whole project. That's Google's default and a known anti-pattern, so we never attach it. Also: Vertex AI is now **Gemini Enterprise Agent Platform** (Apr 2026). Agent Runtime, Sessions/Memory Bank, Evaluation, Observability and Agent Identity come built in, so several Linear issues switch from "build" to "configure". Alexander caught this by checking the current docs.
- **Next:** SMO-9, toolchain and an ADK hello world on Agent Platform.

### ES
- **Qué:** dos cuentas de servicio. `sg-agent` tiene 6 roles (usuario de Agent Platform, cliente de Cloud SQL + usuario IAM de BD, logs, métricas, trazas). `sg-ingestion` tiene 4. Sin claves JSON. Credenciales locales por defecto (ADC). Alexander puede suplantar las dos para probar con sus permisos exactos (probado: se emitió un token). El ADR-002 recoge el modelo, incluida la autenticación IAM en la base de datos (sin contraseña).
- **Por qué:** en n8n las claves vivían en un gestor de credenciales. En Google Cloud el código tiene una identidad propia y Google emite tokens de corta duración, así que no hay nada que se pueda filtrar.
- **Aprendido:** la cuenta de servicio de Compute por defecto trae **Editor** sobre todo el proyecto. Es el valor por defecto de Google y un antipatrón conocido, así que nunca la usamos. Además, Vertex AI ahora es **Gemini Enterprise Agent Platform** (abril 2026). Agent Runtime, Sessions/Memory Bank, Evaluation, Observability y Agent Identity ya vienen incluidos, así que varias tareas de Linear pasan de "construir" a "configurar". Lo detectó Alexander al revisar la documentación actual.
- **Siguiente:** SMO-9, herramientas locales y un hola mundo con ADK sobre Agent Platform.

---

## 4 · Toolchain, ADK hello world, model endpoint decision (SMO-9) — 2026-10-16

### EN
- **What:** uv + Python 3.12 + ADK 2.12. A `hello_agent` with one tool runs in `adk web`, on Agent Platform with Alexander's Google login (no API key). Tested: tool call → result → answer in English and Spanish, including the "not found" case. ADR-003 (ADK) accepted.
- **Why:** in n8n, the AI Agent node hid the loop. In ADK the loop is visible event by event, and a tool is just a Python function whose docstring becomes the tool description.
- **Learned:** **regions decide which models you get.** `europe-west1` serves only Gemini 2.5. Gemini 3.x (including 3.8 Flash, the n8n model) is only on `global` or the EU jurisdictional endpoint `eu`. We chose `eu` + 3.8 Flash: same model as the baseline, processing inside the EU. Also: winget installed uv without adding it to PATH, and `.env` is only read when `adk web` starts.
- **Next:** SMO-10, the vector store ADR and provisioning Cloud SQL + pgvector.

### ES
- **Qué:** uv + Python 3.12 + ADK 2.12. Un `hello_agent` con una herramienta funciona en `adk web`, sobre Agent Platform con el login de Google de Alexander (sin API key). Probado: llamada a la herramienta → resultado → respuesta en inglés y en español, incluido el caso "no encontrado". ADR-003 (ADK) aceptado.
- **Por qué:** en n8n el nodo AI Agent escondía el bucle. En ADK el bucle se ve evento a evento, y una herramienta es solo una función de Python cuyo docstring se convierte en la descripción que lee el modelo.
- **Aprendido:** **la región decide qué modelos tienes.** `europe-west1` solo sirve Gemini 2.5. Gemini 3.x (incluido 3.8 Flash, el modelo de n8n) solo está en `global` o en el endpoint jurisdiccional de la UE, `eu`. Elegimos `eu` + 3.8 Flash: el mismo modelo que la línea base y el procesamiento dentro de la UE. Además: winget instaló uv sin añadirlo al PATH, y el `.env` solo se lee al arrancar `adk web`.
- **Siguiente:** SMO-10, ADR del almacén vectorial y Cloud SQL + pgvector.

---
