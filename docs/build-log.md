# StoreGear on Google Cloud — Build Log / Diario de construcción

Bilingual diary (EN + ES), one entry per Linear issue. It feeds the thesis annex.

| # | Date | Issue | Title |
|---|---|---|---|
| 1 | 2026-10-15 | SMO-6 | Repo, ADR process and project docs |
| 2 | 2026-10-16 | SMO-7 | Google Cloud project, budget and APIs |
| 3 | 2026-10-16 | SMO-8 | Service accounts, least privilege, no keys |
| 4 | 2026-10-16 | SMO-9 | Toolchain, ADK hello world, model endpoint decision |
| 5 | 2026-10-17 | SMO-10 | Vector store: Cloud SQL free trial, schema, least privilege |
| 6 | 2026-10-17 | SMO-11 | Catalog export, embedding benchmark, load |
| 7 | 2026-10-17 | SMO-12 | Hybrid search tool, contextual embeddings |
| 8 | 2026-10-17 | SMO-13 | The StoreGear agent: prompt, tools, pre-retrieval |

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

## 5 · Vector store: Cloud SQL free trial, schema, least privilege (SMO-10) — 2026-10-17

### EN
- **What:** ADR-004 picked Cloud SQL Postgres + pgvector, because the n8n hybrid query (vectors + Spanish full-text + RRF) only runs unchanged on Postgres. Alexander found a **30-day free trial** instance (Enterprise Plus, 8 vCPU, 64 GB, €0) instead of the paid db-f1-micro. The schema is applied as code (`infra/sql/001_schema.sql`): two tables, an HNSW vector index, a GIN Spanish-search index, and IAM database users with grants. The admin password lives in Secret Manager and is read at run time.
- **Why:** same engine and same query as the baseline, so the comparison stays fair. The free trial covers the deadline and frees the budget for models.
- **Learned:** least privilege, tested rather than assumed. Connecting *as* each robot through impersonation: `sg-agent` can read and is refused writes; `sg-ingestion` can write. The free trial never auto-charges (it stops after 30 days), but "Upgrade" would cost hundreds a month. Spanish stemming turns "baterías" into `bat`. Small bug caught: our SQL splitter skipped statements that had trailing comments, so verify after every migration.
- **Next:** SMO-11, export the catalog from n8n, choose the Google embedding model and load it.

### ES
- **Qué:** el ADR-004 eligió Cloud SQL Postgres + pgvector, porque la consulta híbrida de n8n (vectores + búsqueda de texto en español + RRF) solo funciona sin cambios en Postgres. Alexander encontró una instancia de **prueba gratuita de 30 días** (Enterprise Plus, 8 vCPU, 64 GB, 0 €) en lugar de la db-f1-micro de pago. El esquema se aplica como código (`infra/sql/001_schema.sql`): dos tablas, un índice vectorial HNSW, un índice GIN de búsqueda en español y usuarios IAM de base de datos con sus permisos. La contraseña de administrador está en Secret Manager y se lee al ejecutar.
- **Por qué:** el mismo motor y la misma consulta que la línea base, así que la comparación es justa. La prueba gratuita cubre el plazo y libera presupuesto para los modelos.
- **Aprendido:** el mínimo privilegio se prueba, no se supone. Conectando *como* cada robot mediante suplantación: `sg-agent` puede leer y se le deniega escribir; `sg-ingestion` puede escribir. La prueba gratuita nunca cobra sola (se para a los 30 días), pero "Upgrade" costaría cientos de euros al mes. El stemming en español convierte "baterías" en `bat`. Pequeño bug detectado: nuestro separador de SQL se saltaba sentencias con comentarios al final de línea, así que hay que verificar después de cada migración.
- **Siguiente:** SMO-11, exportar el catálogo de n8n, elegir el modelo de embeddings de Google y cargarlo.

---

## 6 · Catalog export, embedding benchmark, load (SMO-11) — 2026-10-17

### EN
- **What:** Alexander exported `catalog_chunks` (9,054) and `catalog_parents` (1,171) from Supabase. We confirmed n8n's Spanish search column is identical to ours. Two Google models embedded the whole catalog and were compared on the 17 eval questions with a known manual. Winner: `gemini-embedding-2`, right manual first 16/17 vs 13/17 for `gemini-embedding-001`, and in the top 5 for 17/17 with both. It was loaded as `sg-ingestion` in 58 s, with 0 orphans. The eval dataset (22 questions) now lives in the repo.
- **Why:** choose by measuring on our own data. Retrieval quality is the foundation of the 5.00 baseline.
- **Learned:** ⚠️ `gemini-embedding-2` returns ONE vector for a list of texts. Batching would have silently merged passages, with no error. Now there's an explicit count check. Also: each embedding model lives on a different endpoint (`001` in europe-west1, `2` only on `eu`).
- **Next:** SMO-12, port the one-query hybrid search as an ADK tool and repeat the 18/18 retrieval check.

### ES
- **Qué:** Alexander exportó `catalog_chunks` (9.054) y `catalog_parents` (1.171) desde Supabase. Confirmamos que la columna de búsqueda en español de n8n es idéntica a la nuestra. Dos modelos de Google embebieron todo el catálogo y los comparamos con las 17 preguntas del eval que tienen manual conocido. Ganador: `gemini-embedding-2`, manual correcto en primer lugar 16/17 frente a 13/17 de `gemini-embedding-001`, y en el top 5 17/17 con los dos. Se cargó como `sg-ingestion` en 58 s, con 0 huérfanos. El dataset del eval (22 preguntas) ya está en el repo.
- **Por qué:** elegir midiendo con nuestros propios datos. La calidad de la recuperación es la base de la puntuación de 5.00.
- **Aprendido:** ⚠️ `gemini-embedding-2` devuelve UN vector para una lista de textos. Mandar lotes habría fusionado pasajes en silencio, sin ningún error. Ahora hay una comprobación explícita del número de vectores. Además, cada modelo de embeddings vive en un endpoint distinto (`001` en europe-west1, `2` solo en `eu`).
- **Siguiente:** SMO-12, portar la búsqueda híbrida de una sola consulta como herramienta de ADK y repetir la prueba de recuperación 18/18.

---

## 7 · Hybrid search tool, contextual embeddings (SMO-12) — 2026-10-17

### EN
- **What:** the n8n hybrid search ported 1:1 as an ADK-ready Python tool. It uses the same SQL, a pooled Cloud SQL connection with IAM auth, `<manual>` spotlighting, and the role passed from the login (never from the model). Benchmarked as `sg-agent`: right manual first 17/17, all needed manuals in the top 5 16/17, median 0.6 s (n8n 1.33 s). Role filter verified.
- **Why:** retrieval is half of answer quality, and it's cheaper to fix here than in the eval.
- **Learned:** measure, look at the misses, fix the cause. The first run scored 15/17: sibling Polar manuals were confused because only 2–3 % of chunks name their product. Embedding `header_path + chunk_text` (contextual embeddings) brought it to 17/17. A per-manual diversity cap didn't fix the comparison question, because the right section was never retrieved. Comparisons need one search per product, which is the agent's job.
- **Next:** SMO-13, the StoreGear agent (prompt, tools, pre-retrieval).

### ES
- **Qué:** la búsqueda híbrida de n8n portada 1:1 como herramienta de Python lista para ADK. Usa el mismo SQL, una conexión a Cloud SQL en pool con autenticación IAM, el etiquetado `<manual>` y el rol pasado desde el login (nunca desde el modelo). Medida como `sg-agent`: manual correcto el primero 17/17, todos los manuales necesarios en el top 5 16/17, mediana 0,6 s (n8n 1,33 s). Filtro por rol verificado.
- **Por qué:** la recuperación es la mitad de la calidad de la respuesta, y es más barato arreglarla aquí que en el eval.
- **Aprendido:** medir, mirar los fallos y arreglar la causa. La primera ejecución dio 15/17: se confundían manuales hermanos de Polar porque solo el 2-3 % de los chunks nombran su producto. Embeber `header_path + chunk_text` (embeddings contextuales) lo subió a 17/17. Un límite de diversidad por manual no arregló la pregunta de comparación, porque la sección correcta ni siquiera se recuperaba. Las comparaciones necesitan una búsqueda por producto, y eso es tarea del agente.
- **Siguiente:** SMO-13, el agente de StoreGear (prompt, herramientas, búsqueda previa).

---

## 8 · The StoreGear agent: prompt, tools, pre-retrieval (SMO-13) — 2026-10-17

### EN
- **What:** ADK agent `storegear`. The n8n system prompt is copied verbatim into git. Tools: `buscar_catalogo_hibrido` and `consultar_precio_stock` (live Google Sheet, shared with sg-agent as Viewer, Sheets API enabled). Pre-retrieval runs as a `before_model_callback`, once per turn. The role comes from session state only. Model: gemini-3.8-flash, thinking low. Spot checks as sg-agent: Q1, Q16, Q18, Q19 and Q20 all behave like n8n. ADR-006 accepted.
- **Why:** behavioural parity first, then measure (SMO-14).
- **Learned:** the comparison question that failed the retrieval benchmark is solved by agent behaviour. The model saw the pre-search covered one product and searched the other. Retrieval benchmarks and agent evals measure different things. Price answers cost two model calls plus a Sheet read (~23 s cold), so latency is the next thing to measure.
- **Next:** SMO-14, the 22-question eval with LLM judges.

### ES
- **Qué:** agente de ADK `storegear`. El prompt de sistema de n8n, copiado literal en git. Herramientas: `buscar_catalogo_hibrido` y `consultar_precio_stock` (Google Sheet en vivo, compartida con sg-agent como lector, Sheets API activada). La búsqueda previa funciona como `before_model_callback`, una vez por turno. El rol sale solo del estado de la sesión. Modelo: gemini-3.8-flash con razonamiento bajo. Pruebas como sg-agent: Q1, Q16, Q18, Q19 y Q20 se comportan como en n8n. ADR-006 aceptado.
- **Por qué:** primero paridad de comportamiento, después medir (SMO-14).
- **Aprendido:** la pregunta de comparación que fallaba en la prueba de recuperación la resuelve el comportamiento del agente. El modelo vio que la búsqueda previa cubría un solo producto y buscó el otro. Las pruebas de recuperación y los evals del agente miden cosas distintas. Las respuestas de precio cuestan dos llamadas al modelo más una lectura de la hoja (~23 s en frío), así que la latencia es lo siguiente que hay que medir.
- **Siguiente:** SMO-14, el eval de 22 preguntas con jueces LLM.

---
