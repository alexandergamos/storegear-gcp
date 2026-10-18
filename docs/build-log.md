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
