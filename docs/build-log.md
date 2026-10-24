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
| 9 | 2026-10-17 | SMO-14 | Eval gate: from 4.77 to 4.95, and the tail-latency trap |
| 10 | 2026-10-18 | SMO-15 | Deploy to Agent Runtime: six laptop-vs-cloud surprises |
| 11 | 2026-10-18 | SMO-16 | Parser bake-off: Gemini vs Document AI |
| 12 | 2026-10-18 | SMO-17 | New catalog: table-aware chunks, Q6 fixed, 43 % fewer tokens |
| 13 | 2026-10-19 | SMO-18 | Injection gate: Gemini 40/40, Model Armor 9/40, catalog clean |
| 14 | 2026-10-20 | SMO-19 | Ingestion queue on Cloud Run: retries, dead letter, alert |
| 15 | 2026-10-21 | SMO-20 | Drive sync + catalog rebuilt by the cloud pipeline |
| 16 | 2026-10-21 | SMO-21 | Threat model: OWASP LLM + Agentic, trifecta kept broken |
| 17 | 2026-10-21 | SMO-22 | Login and roles: Identity Platform + sg-api, 7/7 |
| 18 | 2026-10-21 | SMO-23 | Guardrails + PII at the door, safety settings on, 10/10 |
| 19 | 2026-10-22 | SMO-24 | Sessions with a 30-day TTL, history without the model; Phase 3 gate |
| 20 | 2026-10-24 | SMO-28 | CI/CD with keyless deploys, the eval as a release gate |
| 21 | 2026-10-24 | SMO-25/26 | Traces without text, one line per answer, cost per answer |

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

## 9 · Eval gate: from 4.77 to 4.95, and the tail-latency trap (SMO-14) — 2026-10-17

### EN
- **What:** an eval harness replicating n8n (same dataset, judge prompts copied from Langfuse, same judge model). Run 1: Correctness 4.77, failing the gate; the agent stopped one search early on Q6, Q12 and Q13. Medium thinking fixed it but was 6× slower, so it was rejected. Final: explicit guidance in the pre-retrieval block plus a model-call timeout/retry. **Corr 4.95 · Faith 4.91 · Ctx 5.00 · Ans 5.00 · median 6.2 s** (n8n 5.00/4.95/5.00/5.00, 9.0 s). Gate passed. ADR-007.
- **Why:** a regression gate we can run on every change and later in CI.
- **Learned:** (1) **Tail latency is a different problem from median latency.** The `eu` endpoint's median is ~2.5 s per call, but some calls queued for 30–190 s, with no 429 visible. A 15 s deadline plus retries cuts the tail without leaving the EU. (2) More thinking is the expensive way to fix "stopped too early"; precise guidance is the cheap way. (3) Measure every step: the searches were ~1 s, so the model was the culprit.
- **Next:** SMO-15, deploy to Agent Runtime and measure there.

### ES
- **Qué:** un harness de eval que replica el de n8n (mismo dataset, prompts de los jueces copiados de Langfuse, mismo modelo juez). Ejecución 1: corrección 4,77, suspende el umbral; el agente paraba una búsqueda antes de tiempo en Q6, Q12 y Q13. El razonamiento medio lo arreglaba pero era 6× más lento, así que se descartó. Final: indicaciones explícitas en el bloque de búsqueda previa más un timeout con reintentos en las llamadas al modelo. **Corr 4,95 · Fidel 4,91 · Ctx 5,00 · Resp 5,00 · mediana 6,2 s** (n8n 5,00/4,95/5,00/5,00, 9,0 s). Umbral superado. ADR-007.
- **Por qué:** un control de regresión que podemos ejecutar en cada cambio y, más adelante, en CI.
- **Aprendido:** (1) **la latencia de cola es un problema distinto de la latencia mediana.** El endpoint `eu` tiene una mediana de ~2,5 s por llamada, pero algunas llamadas se quedaban en cola 30–190 s, sin ningún 429 visible. Un límite de 15 s con reintentos recorta la cola sin salir de la UE. (2) Más razonamiento es la forma cara de arreglar "paró demasiado pronto"; unas indicaciones precisas son la forma barata. (3) Medir cada paso: las búsquedas tardaban ~1 s, así que el culpable era el modelo.
- **Siguiente:** SMO-15, desplegar en Agent Runtime y medir allí.

---

## 10 · Deploy to Agent Runtime: six laptop-vs-cloud surprises (SMO-15) — 2026-10-18

### EN
- **What:** ADR-008 picked Agent Runtime (managed, ADK-native, managed Sessions, idle not billed) in the `eu` multi-region, running as `sg-agent`. Deployed from Python (`infra/deploy_agent_runtime.py`). Cloud results: median **3.0 s** (n8n 9.0 s), cold start ~16 s, price and role filter verified. Eval: 4.86 / 5.00 / 4.95 / 5.00. Q6 is a data gap (a spec table row chunked with GPS text), and its fix is assigned to SMO-17 (Alexander's decision). **Phase 1 closed on 18 Oct, three days early.**
- **Why:** a managed runtime next to the model endpoint; the platform runs sessions for us.
- **Learned:** six surprises between laptop and cloud: a bucket in the wrong project; the SDK silently defaulting to us-central1; reserved env var names; the project **number** instead of the ID; metadata tokens ignoring OAuth scopes (Sheets 403); a tool exception killing the turn. Each one is a line in ADR-008. Every fix was explicit configuration rather than a workaround.
- **Next:** Phase 2, ingestion on Google Cloud, starting with the parser choice (SMO-16).

### ES
- **Qué:** el ADR-008 eligió Agent Runtime (gestionado, nativo de ADK, sesiones gestionadas, sin coste en reposo) en la multirregión `eu`, ejecutándose como `sg-agent`. Desplegado desde Python (`infra/deploy_agent_runtime.py`). Resultados en la nube: mediana **3,0 s** (n8n 9,0 s), arranque en frío ~16 s, precio y filtro por rol verificados. Eval: 4,86 / 5,00 / 4,95 / 5,00. Q6 es un hueco de datos (una fila de la tabla de especificaciones troceada junto a texto del GPS), y su arreglo queda asignado a SMO-17 (decisión de Alexander). **Fase 1 cerrada el 18-10, tres días antes de plazo.**
- **Por qué:** un runtime gestionado junto al endpoint del modelo; la plataforma gestiona las sesiones por nosotros.
- **Aprendido:** seis sorpresas entre el portátil y la nube: un bucket en el proyecto equivocado; el SDK que se iba a us-central1 por defecto sin avisar; nombres de variables de entorno reservados; el **número** de proyecto en lugar del ID; tokens de metadatos que ignoran los scopes de OAuth (403 en Sheets); una excepción de una herramienta que tumbaba el turno. Cada una es una línea del ADR-008. Todos los arreglos fueron configuración explícita, no parches.
- **Siguiente:** Fase 2, ingesta en Google Cloud, empezando por elegir el parser (SMO-16).

---

## 11 · Parser bake-off: Gemini vs Document AI (SMO-16) — 2026-10-18

### EN
- **What:** Document AI API enabled; Layout Parser processor `sg-layout-parser` (eu, `8a9ba69484bf2664`). Gemini 3.8 Flash and Layout Parser compared on 3 trap excerpts (`ingestion/parser_test.py`): both kept 9/9 traps. Gemini keeps multi-line cells in one labelled row and gives clean text; Layout Parser splits some cells into label-less rows and has OCR glitches, but it's 2–5× faster and deterministic. Word coverage 97–100 % for both. ADR-009 accepted: Gemini first, a coverage check, Document AI fallback below 95 %.
- **Why:** retrieval quality starts at parsing; Q6 fails because a table row lost its label.
- **Learned:** "the specialised service is cheaper" was an assumption, and it was wrong. Measured: Gemini ≈ $2.6 per 1,000 pages vs Document AI $10. The per-answer price check matches n8n's Langfuse cost. Alexander asked the question that exposed it. A 9/9 tie on traps still hid a real difference in table structure: read the outputs, not just the score.
- **Next:** SMO-17, re-parse and chunk tables row by row, then re-run the cloud eval for Q6.

### ES
- **Qué:** API de Document AI activada; procesador Layout Parser `sg-layout-parser` (eu, `8a9ba69484bf2664`). Gemini 3.8 Flash y Layout Parser comparados en 3 fragmentos con trampas (`ingestion/parser_test.py`): los dos conservaron 9/9. Gemini mantiene las celdas de varias líneas en una sola fila con su etiqueta y da texto limpio; Layout Parser parte algunas celdas en filas sin etiqueta y tiene errores de OCR, pero es 2–5× más rápido y determinista. Cobertura de palabras del 97–100 % en ambos. ADR-009 aceptado: Gemini primero, comprobación de cobertura y Document AI como respaldo por debajo del 95 %.
- **Por qué:** la calidad de la búsqueda empieza al leer el PDF; Q6 falla porque una fila de tabla perdió su etiqueta.
- **Aprendido:** «el servicio especializado es más barato» era una suposición, y era falsa. Medido: Gemini ≈ 2,6 $ por 1.000 páginas frente a 10 $ de Document AI. La comprobación de precio por respuesta cuadra con el coste de Langfuse en n8n. La pregunta que lo destapó la hizo Alexander. Un empate 9/9 en las trampas escondía una diferencia real en la estructura de las tablas: hay que leer los resultados, no solo la nota.
- **Siguiente:** SMO-17, volver a leer los PDFs y trocear las tablas fila a fila; después repetir el eval en la nube para Q6.

---

## 12 · New catalog: table-aware chunks, Q6 fixed, 43 % fewer tokens (SMO-17) — 2026-10-18

### EN
- **What:** full parse of 10 manuals (Gemini, shingle coverage 97.6–98.8 %, Document AI fallback on 3/334 batches); table-aware chunker (one chunk per row, brand-only folding, word caps, icon columns dropped). 12,792 chunks loaded into side tables, benchmarked (top-5 now 17/17), evaluated (4.95 / 5.00 / 5.00 / 5.00), swapped live in one transaction (v1 kept). Cloud eval: 22/22 at 5 when the model answers, Q6 fixed; median 3.8 s; ~5,400 input tokens per answer (was ~9,900).
- **Why:** Q6 was a data problem; fix the data, not the prompt.
- **Learned:** (1) **inspect the output before loading.** Three chunker bugs (over-eager folding that erased feature ownership, unsplit lists, icon columns) would each have silently hurt retrieval; none would have crashed. (2) Side tables plus a transactional rename make a data migration reversible in one statement. (3) Smaller, more precise chunks improved quality *and* cut cost. (4) Availability is now the weakest link: one 504 after 3 × 15 s, to be handled in Phase 4.
- **Next:** SMO-18, prompt-injection check at ingestion.

### ES
- **Qué:** lectura completa de 10 manuales (Gemini, cobertura por shingles del 97,6–98,8 %, respaldo de Document AI en 3/334 lotes); troceado consciente de tablas (un chunk por fila, solo se agrupan las secciones de marca, límite de palabras, columnas de iconos eliminadas). 12.792 chunks cargados en tablas paralelas, medidos (top 5 ahora 17/17), evaluados (4,95 / 5,00 / 5,00 / 5,00) y activados con una sola transacción (v1 se conserva). Eval en la nube: 22/22 con un 5 cuando el modelo responde, Q6 arreglada; mediana 3,8 s; ~5.400 tokens de entrada por respuesta (antes ~9.900).
- **Por qué:** Q6 era un problema de datos; se arreglan los datos, no el prompt.
- **Aprendido:** (1) **revisar el resultado antes de cargar.** Tres errores del troceado (agrupar de más, que borraba qué reloj tiene cada función; listas sin cortar; columnas de iconos) habrían empeorado la búsqueda en silencio; ninguno habría dado un error. (2) Tablas paralelas más un renombrado en una transacción hacen que una migración de datos se pueda deshacer con una sola sentencia. (3) Chunks más pequeños y precisos mejoraron la calidad *y* bajaron el coste. (4) La disponibilidad es ahora el eslabón más débil: un 504 tras 3 × 15 s, que se resolverá en la fase 4.
- **Siguiente:** SMO-18, detección de prompt injection en la ingesta.

---

## 13 · Injection gate: Gemini 40/40, Model Armor 9/40, catalog clean (SMO-18) — 2026-10-19

### EN
- **What:** bake-off of 3 detectors on 240 real sections (140 clean, 60 hard negatives full of commands, 40 with a planted attack in 6 styles): regex 26/40, Gemini 3.8 Flash 40/40, Model Armor 9/40, all 0 false alarms. Gemini also resisted 4 attacks aimed at the classifier itself. JEV (TypeSafe) was considered but there was no API access. ADR-010 accepted: regex tripwire + Gemini classifier, quarantine table, fail closed. First run on the live catalog: 0 quarantined, 26 timeouts caught by fail closed, 1 regex false alarm fixed.
- **Why:** SMO-20 turns the Drive folder into an input surface; poisoned documents are the RAG-specific attack.
- **Learned:** (1) **Know what your guardrail is built for.** Model Armor misses most payloads even alone: it targets direct user jailbreaks, not indirect instructions in documents. (2) Two detectors that fail differently beat one great one: regex can't be argued with, the LLM understands paraphrase. (3) **Fail closed earns its keep immediately:** 0.8 % of checks timed out on the first run. (4) The first false alarm came from real vendor language, not from the test set: the test set is friendly, production isn't.
- **Next:** SMO-19, queue + worker.

### ES
- **Qué:** comparativa de 3 detectores sobre 240 secciones reales (140 limpias, 60 trampa llenas de instrucciones de uso, 40 con un ataque plantado en 6 estilos): regex 26/40, Gemini 3.8 Flash 40/40, Model Armor 9/40, todos sin falsas alarmas. Gemini resistió además 4 ataques dirigidos al propio clasificador. Se consideró JEV (TypeSafe), sin acceso a la API. ADR-010 aceptado: regex como alarma fija + clasificador Gemini, tabla de cuarentena, fallo en cerrado. Primera pasada sobre el catálogo real: 0 en cuarentena, 26 timeouts frenados por el fallo en cerrado, 1 falsa alarma del regex corregida.
- **Por qué:** con SMO-20 la carpeta de Drive pasa a ser una vía de entrada; los documentos envenenados son el ataque propio de un RAG.
- **Aprendido:** (1) **Saber para qué está hecho tu guardrail.** Model Armor falla la mayoría de ataques incluso sueltos: está pensado para jailbreaks directos del usuario, no para instrucciones escondidas en documentos. (2) Dos detectores que fallan de forma distinta ganan a uno muy bueno: al regex no se le convence, el LLM entiende paráfrasis. (3) **El fallo en cerrado sirvió desde el primer día:** el 0,8 % de las comprobaciones hizo timeout. (4) La primera falsa alarma vino de lenguaje real del fabricante, no del set de prueba: el set de prueba es amable; producción, no.
- **Siguiente:** SMO-19, cola + worker.

---

## 14 · Ingestion queue on Cloud Run: retries, dead letter, alert (SMO-19) — 2026-10-20

### EN
- **What:** ADR-011 accepted: a Postgres queue table drained by a Cloud Run job (`sg-ingest-worker`, runs as `sg-ingestion`). Per job: Drive download → parse → chunk → injection gate → embed → replace the manual in one transaction. `UNIQUE (file_id, content_hash, action)` makes enqueues idempotent; `FOR UPDATE SKIP LOCKED` claims; exponential backoff; 3 attempts → `dead` + `INGEST_DEAD` log line → log-based email alert; stale claims reaped. Tested locally (happy path, retry, dead, stale) and in the cloud: first run 403 (Drive API off) → retried → done, 10 chunks in 20 s.
- **Why:** Phase 2 needs ingestion to run unattended and be safe to retry; the table is the state machine, so a managed queue would only add pieces at 10 manuals a month.
- **Learned:** (1) **Retries belong to one layer.** Cloud Run job `max-retries = 0`, because the queue already retries. (2) **Check what the Console actually did.** The job ran as the default Compute account (Editor) and Token Creator sat at project level for both service accounts; `get-iam-policy` caught both. Same role, two levels, very different blast radius. (3) **`.gcloudignore` decides what reaches Cloud Build, not `.dockerignore`.** A whitelist keeps the manuals on the laptop. (4) The failure path proved itself on day one: the Drive 403 was logged, retried and recovered without anyone touching the database.
- **Next:** SMO-20, Drive sync on a schedule.

### ES
- **Qué:** ADR-011 aceptado: una tabla de cola en Postgres que vacía un job de Cloud Run (`sg-ingest-worker`, se ejecuta como `sg-ingestion`). Por cada trabajo: descarga de Drive → lectura → troceado → filtro de injection → embeddings → sustituir el manual en una transacción. `UNIQUE (file_id, content_hash, action)` hace que encolar sea idempotente; `FOR UPDATE SKIP LOCKED` reparte el trabajo; reintentos con espera exponencial; 3 intentos → `dead` + línea `INGEST_DEAD` → alerta por email; los trabajos colgados se recuperan. Probado en local (camino feliz, reintento, muerto, colgado) y en la nube: primera ejecución 403 (API de Drive apagada) → reintento → hecho, 10 chunks en 20 s.
- **Por qué:** la fase 2 necesita que la ingesta funcione sola y se pueda repetir sin riesgo; la tabla ya es la máquina de estados, así que una cola gestionada solo añadiría piezas para 10 manuales al mes.
- **Aprendido:** (1) **Los reintentos, en una sola capa.** El job de Cloud Run va con `max-retries = 0` porque la cola ya reintenta. (2) **Comprobar lo que la consola hizo de verdad.** El job se ejecutaba con la cuenta por defecto de Compute (Editor) y Token Creator estaba a nivel de proyecto para las dos cuentas de servicio; `get-iam-policy` destapó las dos cosas. El mismo rol en dos niveles tiene un alcance muy distinto. (3) **Lo que se sube a Cloud Build lo decide `.gcloudignore`, no `.dockerignore`.** Una lista blanca mantiene los manuales en el portátil. (4) El camino de fallo se probó solo el primer día: el 403 de Drive se registró, se reintentó y se recuperó sin tocar la base de datos.
- **Siguiente:** SMO-20, sincronización con Drive programada.

---

## 15 · Drive sync + catalog rebuilt by the cloud pipeline (SMO-20) — 2026-10-21

### EN
- **What:** ADR-012: a reconciliation loop (`ingestion/sync.py`, run by the job with `--sync`) compares Drive (desired) with the queue and catalog (actual) and enqueues upserts, moves (version key `md5:access`) and deletes; an empty listing never deletes. Full rebuild into `_v3` by 3 parallel tasks in 31 min; `fold_common` rebuilt the 13 shared Polar sections; eval 4.95/5/5/5; swapped live with the queue history. Cloud Scheduler every 15 min, verified (SYNC_DONE 10 listed, 0 queued).
- **Why:** Drive is the source of truth; the catalog must follow it without anyone running scripts.
- **Learned:** (1) **Reconciliation beats events** at this scale: it can't miss a change, and a failed run is fixed by the next one. (2) **Parallel workers for free:** `SKIP LOCKED` meant three Cloud Run tasks shared the queue with zero coordination code, and a 504 on one manual was absorbed by another worker. (3) **Move the bookkeeping with the data:** the swap also re-targets the queue rows, or the live sync would have re-ingested everything.
- **Also learned:** a newly enabled API (Cloud Scheduler) dispatched nothing for ~1 h 45 min; and Cloud Run job arguments REPLACE the image CMD (use ENTRYPOINT).
- **Next:** SMO-21.

### ES
- **Qué:** ADR-012: un bucle de reconciliación (`ingestion/sync.py`, lo ejecuta el job con `--sync`) compara Drive (estado deseado) con la cola y el catálogo (estado real) y encola altas, cambios, movimientos (clave de versión `md5:acceso`) y bajas; un listado vacío nunca borra. Reconstrucción completa en `_v3` con 3 tareas en paralelo en 31 min; `fold_common` recreó las 13 secciones comunes de Polar; eval 4,95/5/5/5; activado junto con el historial de la cola. Cloud Scheduler cada 15 min, verificado (SYNC_DONE: 10 listados, 0 encolados).
- **Por qué:** Drive es la fuente de verdad; el catálogo tiene que seguirla sin que nadie lance scripts.
- **Aprendido:** (1) **La reconciliación gana a los eventos** a esta escala: no puede perder un cambio, y una ejecución fallida la arregla la siguiente. (2) **Workers en paralelo gratis:** con `SKIP LOCKED`, tres tareas de Cloud Run se repartieron la cola sin código de coordinación, y un 504 en un manual lo absorbió otro worker. (3) **Mover la contabilidad con los datos:** el cambio de tablas también reasigna las filas de la cola; si no, la sincronización habría vuelto a procesarlo todo.
- **También:** una API recién activada (Cloud Scheduler) no ejecutó nada durante ~1 h 45 min; y los argumentos de un job de Cloud Run SUSTITUYEN al CMD de la imagen (hay que usar ENTRYPOINT).
- **Siguiente:** SMO-21.

---

## 16 · Threat model: OWASP LLM + Agentic, trifecta kept broken (SMO-21) — 2026-10-21

### EN
- **What:** `docs/threat-model.md`: assets, actors, entry points; the lethal trifecta check; every item of the OWASP Top 10 for LLM Applications 2025 and the OWASP Top 10 for Agentic Applications (Dec 2025) mapped to a control or an accepted-risk note. ADR-013 accepted: five-layer defence in depth, access control never in the prompt, HITL rule for any action tool.
- **Why:** know what we defend before building defences; it set the order of SMO-22 and SMO-23.
- **Learned:** (1) **The biggest gap was not exotic:** the caller set the role. (2) **The trifecta is broken by design** (no outbound tools), and the residual channel is the answer itself (links, phone numbers), which goes into SMO-23 as an output rule. (3) Check the source: a "2026 edition" of the OWASP LLM list appears in third-party posts, but the official pages still publish 2025.
- **Next:** SMO-22.

### ES
- **Qué:** `docs/threat-model.md`: activos, actores, puntos de entrada; la comprobación de la "lethal trifecta"; cada riesgo del OWASP Top 10 para aplicaciones LLM 2025 y del OWASP Top 10 para aplicaciones agénticas (dic. 2025) asociado a un control o a un riesgo aceptado con su motivo. ADR-013 aceptado: defensa en profundidad en cinco capas, el control de acceso nunca en el prompt, aprobación humana para cualquier herramienta que actúe.
- **Por qué:** saber de qué nos defendemos antes de construir defensas; ordenó SMO-22 y SMO-23.
- **Aprendido:** (1) **El mayor hueco no era exótico:** quien llamaba elegía el rol. (2) **La trifecta está rota por diseño** (ninguna herramienta envía datos fuera), y el canal residual es la propia respuesta (enlaces, teléfonos), que pasa a SMO-23 como regla de salida. (3) Comprobar la fuente: una "edición 2026" de la lista OWASP aparece en artículos de terceros, pero las páginas oficiales siguen publicando la de 2025.
- **Siguiente:** SMO-22.

---

## 17 · Login and roles: Identity Platform + sg-api, 7/7 (SMO-22) — 2026-10-21

### EN
- **What:** ADR-014 accepted. Identity Platform (email/password only, sign-up disabled, API key restricted to the two auth APIs). `sg-api` on Cloud Run verifies the ID token, takes the role from a custom claim set only by `infra/users.py`, rate-limits per user in Cloud SQL, and calls Agent Runtime as `sg-api`. `eval/auth_tests.py` 7/7 on the deployed service: 401, 401, 403, staff without internal figures, manager with them, role in the body ignored, 429.
- **Why:** the threat model's top gap: the caller chose the role.
- **Learned:** (1) **IAP was out** for a reason worth knowing: its direct Cloud Run mode needs an organization, and a personal project has none. (2) **"Public" Cloud Run + app-level auth** is the right pattern when users aren't Google Cloud principals; the 401 comes before any work. (3) **Defaults are broad again:** Firebase's auto-created key was open to ~25 APIs, including Cloud SQL Admin. (4) Two small traps: Cloud Run reserves paths ending in "z" (`/healthz`), and the Cloud SQL connector needs the `cloud-platform` scope.
- **Next:** SMO-23 guardrails.

### ES
- **Qué:** ADR-014 aceptado. Identity Platform (solo email y contraseña, registro desactivado, clave de API limitada a las dos APIs de autenticación). `sg-api` en Cloud Run verifica el token, toma el rol de un claim que solo asigna `infra/users.py`, limita peticiones por usuario en Cloud SQL y llama a Agent Runtime como `sg-api`. `eval/auth_tests.py` 7/7 sobre el servicio desplegado: 401, 401, 403, staff sin cifras internas, encargado con ellas, rol en el cuerpo ignorado, 429.
- **Por qué:** el hueco principal del modelo de amenazas: quien llamaba elegía el rol.
- **Aprendido:** (1) **IAP quedó fuera** por un motivo que conviene saber: su modo directo en Cloud Run exige una organización, y un proyecto personal no la tiene. (2) **Cloud Run "público" + autenticación en la app** es el patrón correcto cuando los usuarios no son identidades de Google Cloud; el 401 llega antes de cualquier trabajo. (3) **Los valores por defecto vuelven a ser amplios:** la clave que creó Firebase estaba abierta a ~25 APIs, incluida Cloud SQL Admin. (4) Dos trampas pequeñas: Cloud Run reserva las rutas que acaban en "z" (`/healthz`), y el conector de Cloud SQL necesita el scope `cloud-platform`.
- **Siguiente:** SMO-23, guardrails.

---

## 18 · Guardrails + PII at the door, safety settings on (SMO-23) — 2026-10-21

### EN
- **What:** ADR-015 accepted. In `sg-api`: deterministic PII masking first (email, ES phone, DNI/NIE with check letter, IBAN mod-97, card Luhn), then Model Armor (`sg-guard`, eu) and a Gemini topic check in parallel, fail closed; on output a deterministic leak check (tool names, internal ids, 12-word overlaps with the prompt minus its quoted reply templates), a link allowlist, PII again and Model Armor's response filters. In the agent: explicit safety settings and `file_id` validation. `eval/guardrail_tests.py` 10/10 incl. the n8n cases and the 22 questions with no false blocks. Eval 5.00 on the second run (4.64 on the first: a 504 and a retrieval miss).
- **Why:** the threat model's input/output items (LLM01, LLM02, LLM05, LLM07, ASI02).
- **Learned:** (1) **Gemini's harm filters are OFF by default** from 2.5 on; nobody notices until they check. (2) **Deterministic first:** a DNI check letter is exact and free; an LLM is for what a rule can't decide (topic). (3) **Encode past false positives as tests:** n8n's two (manager policy as off-topic, "documento interno" as a leak) are now permanent cases. (4) **One eval run is not a gate:** the same agent scored 4.64 and 5.00 an hour apart.
- **Next:** SMO-24 sessions and retention.

### ES
- **Qué:** ADR-015 aceptado. En `sg-api`: primero el enmascarado determinista de datos personales (email, teléfono español, DNI/NIE con letra de control, IBAN mod-97, tarjeta Luhn); después Model Armor (`sg-guard`, eu) y un control de tema con Gemini en paralelo, fallando en cerrado; a la salida, un detector determinista de filtraciones (nombres de herramientas, identificadores internos, coincidencias de 12 palabras con el prompt sin sus plantillas de respuesta), una lista de dominios permitidos para los enlaces, datos personales otra vez y los filtros de respuesta de Model Armor. En el agente: filtros de seguridad explícitos y validación de `file_id`. `eval/guardrail_tests.py` 10/10, incluidos los casos de n8n y las 22 preguntas sin ningún bloqueo falso. Eval 5,00 en la segunda ejecución (4,64 en la primera: un 504 y un fallo de búsqueda).
- **Por qué:** los puntos de entrada y salida del modelo de amenazas (LLM01, LLM02, LLM05, LLM07, ASI02).
- **Aprendido:** (1) **Los filtros de daño de Gemini vienen APAGADOS por defecto** desde la 2.5; nadie lo nota hasta que lo comprueba. (2) **Primero lo determinista:** la letra de un DNI es exacta y gratis; el LLM, para lo que una regla no puede decidir (el tema). (3) **Convertir los falsos positivos pasados en tests:** los dos de n8n (política de encargado como fuera de tema, "documento interno" como filtración) son ahora casos permanentes. (4) **Una sola ejecución del eval no es una barrera:** el mismo agente sacó 4,64 y 5,00 con una hora de diferencia.
- **Siguiente:** SMO-24, sesiones y retención.

---

## 19 · Sessions with a 30-day TTL, history without the model; Phase 3 gate (SMO-24) — 2026-10-22

### EN
- **What:** ADR-016 accepted: Agent Platform Sessions with a 30-day TTL set by `sg-api` (1 day for tests), history endpoints with no model call, a retention audit (144 sessions moved from the 365-day default), no Memory Bank. `session_tests` 6/6 (follow-up, history 0.39 s, cross-user 404 ×3, 30.00-day expiry, delete). Phase 3 gate: remote eval 5.00 / 4.91 / 5.00 / 5.00 after raising the sections given to the agent from 5 to 7.
- **Why:** per-employee conversations with privacy by design (GDPR storage limitation, right to erasure).
- **Learned:** (1) **Check the platform default:** sessions lived a year unless told otherwise. (2) **The gate found a real retrieval weakness:** the rebuilt catalog pushed one answer from 5th to 7th; the duplicate question doubled the hit. (3) **The eval itself had a bug:** in remote mode it rebuilt the judge's context with 5 sections while the agent used 7, so correct answers were scored as unfaithful. The harness now mirrors the deployed settings. (4) **Availability is the new top risk:** one run lost 9 of 22 questions to Google 500/504 errors.
- **Next:** SMO-27 (moved up), then SMO-25/26.

### ES
- **Qué:** ADR-016 aceptado: Agent Platform Sessions con un TTL de 30 días que fija `sg-api` (1 día para tests), historial sin llamar al modelo, una auditoría de retención (144 sesiones pasaron del valor por defecto de 365 días) y sin Memory Bank. `session_tests` 6/6 (seguimiento, historial en 0,39 s, 404 entre usuarios ×3, caducidad a 30,00 días, borrado). Barrera de la fase 3: eval remoto 5,00 / 4,91 / 5,00 / 5,00 tras subir de 5 a 7 las secciones que recibe el agente.
- **Por qué:** conversaciones por empleado con privacidad desde el diseño (limitación del plazo de conservación, derecho de supresión).
- **Aprendido:** (1) **Revisar el valor por defecto de la plataforma:** las sesiones vivían un año si nadie decía lo contrario. (2) **La barrera encontró una debilidad real de búsqueda:** el catálogo reconstruido empujó una respuesta del 5.º al 7.º puesto, y la pregunta duplicada dobló el golpe. (3) **El propio eval tenía un fallo:** en modo remoto reconstruía el contexto del juez con 5 secciones mientras el agente usaba 7, y puntuaba respuestas correctas como infieles. Ahora replica la configuración desplegada. (4) **La disponibilidad es el nuevo riesgo principal:** una ejecución perdió 9 de 22 preguntas por errores 500/504 de Google.
- **Siguiente:** SMO-27 (adelantado), luego SMO-25/26.

---

## 20 · CI/CD with keyless deploys, the eval as a release gate (SMO-28) — 2026-10-24

### EN
- **What:** ADR-018 accepted (option A). Four GitHub Actions workflows: `ci` runs the offline tests on every push; `deploy sg-api` runs on every merge to `main`, signs in to Google Cloud as `sg-deploy` with Workload Identity Federation (no key), builds and pushes the image, deploys a revision with no traffic under the tag `candidate`, smoke-checks it (`/health`, `/status`, `/catalog/models` → 200; `/chat`, `/compare` without a login → 401) and only then moves 100 % of traffic; `eval gate` is started by hand from `main` and runs the 22 questions against the deployed agent (availability failures retried once, every metric ≥ the n8n baseline − 0.1); `retention audit` runs weekly as `sg-ops`. An `api` dependency group slims the `sg-api` image from 126 to 97 MB (−23 %). First CI deploys: `sg-api-00013` and `sg-api-00015`, both through the smoke checks.
- **Why:** the 9–10 band of the rubric asks for CI/CD; deploys from a laptop with personal credentials leave no record and can't be repeated by anyone else.
- **Learned:** (1) **GitHub sends the immutable subject** (owner and repository with their numeric ids), not `repo:OWNER/REPO`: the first deploy failed with `getAccessToken` denied until the bindings used it. Check it with `gh api repos/OWNER/REPO/actions/oidc/customization/sub`. (2) **Required reviewers on environments aren't available** for a private repo on this plan; a `main`-only branch policy and a single collaborator do the same job, and the ADR says so. (3) **A tagged candidate revision** lets the smoke checks hit the new code before any user does. (4) **Test the gate with nothing to grade:** in its first run the model endpoint failed on all 22 questions, and the script crashed on an empty mean instead of failing with a reason. It now closes the gate with "no answer scored", and a question the judge couldn't score is retried like an availability error.
- **Next:** SMO-25/26, traces and cost per answer.

### ES
- **Qué:** ADR-018 aceptado (opción A). Cuatro workflows de GitHub Actions: `ci` pasa los tests sin conexión en cada push; `deploy sg-api` se lanza con cada merge a `main`, entra en Google Cloud como `sg-deploy` con Workload Identity Federation (sin clave), construye y sube la imagen, despliega una revisión sin tráfico con la etiqueta `candidate`, la comprueba (`/health`, `/status`, `/catalog/models` → 200; `/chat`, `/compare` sin login → 401) y solo entonces le pasa el 100 % del tráfico; `eval gate` se lanza a mano desde `main` y pasa las 22 preguntas contra el agente desplegado (los fallos de disponibilidad se reintentan una vez; cada métrica ≥ la referencia de n8n − 0,1); `retention audit` se ejecuta cada semana como `sg-ops`. Un grupo de dependencias `api` reduce la imagen de `sg-api` de 126 a 97 MB (−23 %). Primeros despliegues desde CI: `sg-api-00013` y `sg-api-00015`, los dos superaron las comprobaciones.
- **Por qué:** la banda 9–10 de la rúbrica pide CI/CD; desplegar desde el portátil con credenciales personales no deja rastro y nadie más puede repetirlo.
- **Aprendido:** (1) **GitHub envía el subject inmutable** (propietario y repositorio con sus identificadores numéricos), no `repo:OWNER/REPO`: el primer despliegue falló con `getAccessToken` denegado hasta que los permisos usaron ese formato. Se comprueba con `gh api repos/OWNER/REPO/actions/oidc/customization/sub`. (2) **Los revisores obligatorios en los entornos no están disponibles** para un repo privado en este plan; una regla de solo `main` y un único colaborador cumplen la misma función, y el ADR lo dice. (3) **Una revisión candidata con etiqueta** permite comprobar el código nuevo antes de que llegue ningún usuario. (4) **Probar la barrera sin nada que puntuar:** en su primera ejecución el endpoint del modelo falló en las 22 preguntas y el script se cayó con una media vacía en vez de fallar con un motivo. Ahora cierra la barrera con "no answer scored", y una pregunta que el juez no pudo puntuar se reintenta como un error de disponibilidad.
- **Siguiente:** SMO-25/26, trazas y coste por respuesta.

---

## 21 · Traces without text, one line per answer, cost per answer (SMO-25/26) — 2026-10-24

### EN
- **What:** ADR-019 accepted (option A). The agent is redeployed with Agent Runtime telemetry on and message content capture off, so Cloud Trace shows model calls, tool calls, latency and tokens with no prompt or answer. `sg-api` writes one `ANSWER` line per answer: steps and their times, guard outcome, tokens in / cached / out, model calls, the release (the commit CI deployed), cost in EUR and USD and a hash of the user id; never the question or the answer (a unit test fails if either appears). Prices come from the billing export in BigQuery: Gemini 3.8 Flash Regional EU at €1.452 / €0.145 cached / €7.26 per million tokens. Log-based metrics, a Cloud Monitoring dashboard and an email alert at 3+ failed answers in an hour. `eval/cost_report.py` compares the week's estimate with the bill (±15 %). 8 new tests; 133 offline tests pass.
- **Why:** the rubric's monitoring module, and threat-model items LLM02 (no personal data in traces) and LLM10 (cost and alerts).
- **Learned:** (1) **The list price isn't what you pay:** dividing cost by usage per SKU in the billing export gave this project's real rates, in EUR. (2) **Thinking tokens are billed as output**, so a "short" answer can cost more than its length suggests. (3) **Not every call reports its tokens:** the topic check is a fixed estimate (~300 in, 20 out) that the weekly report keeps honest. (4) **Keep config files in ASCII:** gcloud on Windows mangled a middle dot in the dashboard name. (5) **Still to check on live answers:** one trace opened to confirm it holds no text, and the first real `ANSWER` line with tokens and cost.
- **Next:** SMO-27, what happens when Google's endpoint fails.

### ES
- **Qué:** ADR-019 aceptado (opción A). El agente se vuelve a desplegar con la telemetría de Agent Runtime activada y la captura del contenido de los mensajes desactivada, así que Cloud Trace muestra las llamadas al modelo y a las herramientas, la latencia y los tokens sin la pregunta ni la respuesta. `sg-api` escribe una línea `ANSWER` por respuesta: los pasos y sus tiempos, el resultado de los guardarraíles, los tokens de entrada / en caché / de salida, las llamadas al modelo, la versión (el commit que desplegó CI), el coste en EUR y USD y un hash del identificador del usuario; nunca la pregunta ni la respuesta (un test unitario falla si aparece alguna). Los precios salen de la exportación de facturación en BigQuery: Gemini 3.8 Flash Regional EU a 1,452 € / 0,145 € en caché / 7,26 € por millón de tokens. Métricas basadas en logs, un panel en Cloud Monitoring y una alerta por email con 3 o más respuestas fallidas en una hora. `eval/cost_report.py` compara la estimación de la semana con la factura (±15 %). 8 tests nuevos; pasan los 133 tests sin conexión.
- **Por qué:** el módulo de monitorización de la rúbrica y los puntos LLM02 (sin datos personales en las trazas) y LLM10 (coste y alertas) del modelo de amenazas.
- **Aprendido:** (1) **El precio de tarifa no es lo que pagas:** dividir coste entre uso por SKU en la exportación de facturación dio las tarifas reales del proyecto, en euros. (2) **Los tokens de razonamiento se facturan como salida**, así que una respuesta "corta" puede costar más de lo que parece. (3) **No todas las llamadas informan de sus tokens:** el control de tema es una estimación fija (~300 de entrada, 20 de salida) que el informe semanal vigila. (4) **Ficheros de configuración en ASCII:** gcloud en Windows estropeó un punto medio en el nombre del panel. (5) **Queda comprobarlo con respuestas reales:** abrir una traza para confirmar que no contiene texto y ver la primera línea `ANSWER` real con tokens y coste.
- **Siguiente:** SMO-27, qué pasa cuando falla el endpoint de Google.

---
