# StoreGear on Google Cloud — threat model (SMO-21)

*2026-10-21. Reviewed against the OWASP Top 10 for LLM Applications **2025** (the edition published on owasp.org and genai.owasp.org; a 2026 edition is reported by third parties but wasn't on the official pages when checked) and the OWASP Top 10 for **Agentic** Applications (published 9 Dec 2025). Decision record: ADR-013.*

Rule for this document: **every risk has a control (built or planned, with its issue) or an accepted-risk note with the reason.**

## 1. The system in one picture

```
 shop staff / manager ──(E1: agent API; SMO-22 adds login + token)──▶ Agent Runtime (eu) · ADK agent · sg-agent
                                                                        │  pre-retrieval + 2 READ-ONLY tools
                                                                        ├─▶ buscar_catalogo_hibrido → Cloud SQL (catalog, role filter in SQL)
                                                                        └─▶ consultar_precio_stock  → Google Sheet (read-only scope)
 anyone with write access to Drive ──(E2: "Shop Assitant" + "Internal (manager)")──▶ Cloud Run job · sg-ingestion
                                        parse → chunk → injection gate (regex + Gemini) → quarantine | catalog
 Alexander ──(E4: Console / gcloud / git)──▶ project storegear-prod-ag26 (IAM, budget, deploys)
 dependencies ──(E5: PyPI via uv.lock, base images, Gemini models)──▶ agent + worker images
```

## 2. Assets (what an attacker would want)

| # | Asset | Why it matters | Sensitivity |
|---|---|---|---|
| A1 | **Internal document** (supplier costs, margins, discount policy, targets; demo data) | Manager-only; leaking it to staff or customers is the main confidentiality risk | High |
| A2 | **Price and stock sheet** | Wrong prices in answers cost money and trust | Medium (integrity) |
| A3 | **Catalog** (manual sections + embeddings) | Poisoned content steers every answer | Medium (integrity) |
| A4 | **Conversations** (Agent Platform sessions) | Staff may type customer names, phones, DNI | High (personal data, GDPR) |
| A5 | System prompt, tool design | Helps an attacker craft injections; contains no secrets | Low |
| A6 | Budget and quota | Unbounded use = money and denial of service | Medium |
| A7 | Service accounts `sg-agent`, `sg-ingestion` | Their permissions are the blast radius of any compromise | High |

## 3. Actors

| Actor | Trust | Typical threat |
|---|---|---|
| Shop staff (authenticated) | Medium: legitimate, but must not see manager data | Curiosity or a "jailbreak" to read margins; pretending to be a manager |
| Manager | Higher | Same as staff, plus mistakes |
| Anyone who can write to the Drive folders | Must be treated as **untrusted content** | Indirect prompt injection via a planted PDF (ADR-010) |
| Vendors (Garmin, Polar, Suunto PDFs) | Third-party content | Accidental instructions or misleading text; rare deliberate attacks |
| External attacker | None | Reaching the agent API without an account; burning the budget |
| Alexander / CI | Admin | Misconfiguration (two found already, see ADR-002 addendum) |
| Dependency authors | Implicit trust | Malicious or vulnerable packages and images |

## 4. Entry points

| # | Entry point | Today | After Phase 3 |
|---|---|---|---|
| E1 | Agent API (Agent Runtime `query`) | Only Google principals with Agent Platform permissions can call it; **the caller sets the role in session state** | Login + verified token; role read from the token (SMO-22) |
| E2 | Drive folders | Shared with `sg-ingestion` (Viewer); every section checked by the injection gate before loading | Same, plus alert on quarantine |
| E3 | Price sheet | Read-only to the agent (`spreadsheets.readonly`) | Same; **editors of the sheet = who controls prices** (to confirm) |
| E4 | Console / gcloud / git | Owner = Alexander; budget cap | CI/CD with the eval as a gate (SMO-28) |
| E5 | Dependencies and images | `uv.lock` pins every package; `uv` image pinned by version; base image `python:3.12-slim` by tag | Pin base image by digest; dependency scan in CI (SMO-28) |

## 5. Lethal trifecta check

Simon Willison's "lethal trifecta": an agent is exploitable for data theft when it has **(1) access to private data**, **(2) exposure to untrusted content** and **(3) a way to communicate externally**.

| Leg | StoreGear | |
|---|---|---|
| 1. Private data | Yes: internal document (A1), prices (A2), conversations (A4) | present |
| 2. Untrusted content | Yes: manuals and anything dropped into Drive (E2) | present |
| 3. External communication | **No tool sends anything out.** Both tools are read-only; no email, web fetch, write, or code execution | **absent** |

**The trifecta is broken by design, and the rule that keeps it broken:** *no tool that writes, sends or fetches from outside is added without a human approving each action (HITL) and a new review of this document* (ADR-013).

**Residual channel: the answer itself.** A poisoned section could make the agent print a link or a phone number ("llama a soporte en …") that a person then follows, or a Markdown image whose URL carries data if a front end renders it. Controls: the injection gate (ADR-010), plus an **output rule in SMO-23**: links and phone numbers in answers must come from the cited section, and the front end renders answers as plain text, never remote images.

## 6. OWASP Top 10 for LLM Applications 2025 → our design

| Risk | Where it applies to us | Control (built ✅ / planned ⏳) or accepted risk |
|---|---|---|
| **LLM01 Prompt Injection** | Direct: staff typing "ignora tus instrucciones…". Indirect: instructions hidden in a manual (E2) | ✅ Injection gate at ingestion, regex + Gemini, quarantine, fail closed (ADR-010) · ✅ Spotlighting: sections wrapped in `<manual …>` tags, tag breakouts neutralised · ✅ Role never taken from text · ⏳ Model Armor on user input, the use it's built for (SMO-23) |
| **LLM02 Sensitive Information Disclosure** | Internal document to staff; personal data in conversations and logs | ✅ **Role filter in SQL** (the model never sees manager sections for a staff request) · ✅ Catalog grants per service account · ⏳ Role from a verified token (SMO-22) · ⏳ PII masking on input/output (SMO-23) · ⏳ 30-day session retention (SMO-24) · ⏳ No PII in logs and traces (SMO-25) |
| **LLM03 Supply Chain** | PyPI packages, base images, the Gemini model | ✅ `uv.lock` pins versions; images built from the lock · ✅ Models only from Agent Platform (Google) · ⏳ Base image by digest + dependency scan in CI (SMO-28) |
| **LLM04 Data and Model Poisoning** | Poisoned manuals feed the catalog; no fine-tuning | ✅ Injection gate + human review of quarantine (ADR-010) · ✅ Drive is the only source; the catalog is rebuilt from it (ADR-012) · Accepted: misleading *factual* text in a vendor manual (not an instruction) isn't detected; vendors are a trusted source |
| **LLM05 Improper Output Handling** | Answers shown in a UI; tool arguments built by the model | ✅ Tool arguments are parameters to fixed SQL / a sheet lookup, never code or SQL text · ⏳ Plain-text rendering, no remote images; links and phones only from cited sections (SMO-23, §5) |
| **LLM06 Excessive Agency** | What the agent can *do* | ✅ Two read-only tools · ✅ `sg-agent`: read-only on the catalog, Sheets read-only scope, Token Creator only on itself (ADR-002 addendum) · ✅ HITL rule for any future action tool (ADR-013) |
| **LLM07 System Prompt Leakage** | The prompt could be extracted | **Accepted:** the prompt holds no secrets, keys or access rules; access control lives in SQL and IAM, not in the prompt (the n8n lesson: "telling the LLM not to show it is not security") · ⏳ Output check for prompt-leak patterns (SMO-23) |
| **LLM08 Vector and Embedding Weaknesses** | Staff and manager data in the same tables | ✅ Access filter applied **inside the search SQL** on `access_level`, before ranking · ✅ The agent's DB user can only read · Accepted: embedding inversion is not a meaningful risk for public manuals; the internal document is protected by the filter, not by embedding secrecy |
| **LLM09 Misinformation** | Wrong specs or prices → lost sales | ✅ Answers grounded in retrieved sections, with the source cited · ✅ "No lo sé" for products outside the catalog (eval Q19) · ✅ Prices only from the sheet · ✅ 22-question eval gate at every phase · ⏳ Eval in CI before every deploy (SMO-28) |
| **LLM10 Unbounded Consumption** | Anyone flooding the agent; runaway retries | ✅ Budget alerts (ADR-001; the hard cap returns after the jury week, ~€50) · ✅ Agent Runtime max 2 instances · ✅ Model timeout 15 s, one attempt, then the backup model with 2 attempts · ✅ Ingestion: 3 attempts then dead · ✅ Authentication + rate limiting per user (SMO-22) · ✅ Cost per answer + alerts (SMO-26, SMO-27) |

## 7. OWASP Top 10 for Agentic Applications (Dec 2025) → our design

| Risk | Applies? | Control or accepted risk |
|---|---|---|
| ASI01 Agent Goal Hijack | Yes (= prompt injection aimed at the agent's goal) | See LLM01 |
| ASI02 Tool Misuse & Exploitation | Low: 2 read-only tools | ✅ Fixed queries; ⏳ validate `file_id` format in `consultar_precio_stock` before the lookup (SMO-23) |
| ASI03 Identity & Privilege Abuse | Yes: role spoofing; over-privileged service accounts | ⏳ **Today the caller sets the role**: fixed by SMO-22 (role only from a verified token) · ✅ Least-privilege SAs, no keys, Token Creator self-only, job runs as `sg-ingestion` (two misconfigurations found and fixed on 20 Oct) |
| ASI04 Agentic Supply Chain | Yes | See LLM03 |
| ASI05 Unexpected Code Execution | **No**: no code-execution tool | Accepted (N/A); would need a sandbox + ADR if ever added |
| ASI06 Memory & Context Poisoning | Partly: sessions keep conversation history | ✅ Sessions are per user; no shared long-term memory (Memory Bank not enabled) · ⏳ Retention 30 days (SMO-24) · Rule: enabling Memory Bank needs per-user scoping and a review |
| ASI07 Insecure Inter-Agent Communication | **No**: single agent | Accepted (N/A) until SMO-31 (MCP/A2A exposure, backlog) |
| ASI08 Cascading Failures | Partly | ✅ Bounded retries everywhere, dead letter + alert for ingestion · ✅ Friendly failure reply + alert for the agent · ✅ backup model in the EU when the `eu` endpoint is overloaded (SMO-27) |
| ASI09 Human-Agent Trust Exploitation | Yes: staff may over-trust answers | ✅ Source cited in every answer · ✅ "No lo sé" instead of guessing · Accepted: final responsibility for a sale stays with the employee |
| ASI10 Rogue Agents | **No**: no autonomy beyond a single request | Accepted (N/A) |

## 8. Answers from Alexander (2026-10-21)

1. **Price sheet (E3):** only Alexander (manager) can edit it. Accepted risk: a single editor, so integrity depends on his account (2-step verification recommended).
2. **Drive folders (E2):** only Alexander can write to them. The injection gate stays as defence in depth for vendor PDFs and a compromised account.

## 9. Order of the remaining work (what this threat model changes)

1. **SMO-22 first**: the biggest open gap is that *the caller decides the role* (ASI03, LLM02). Until a verified token decides it, the role filter protects nothing against a caller who lies.
2. **SMO-23**: Model Armor on user input (its design target), PII masking, the output rule for links, phones and images (§5), `file_id` validation.
3. **SMO-24 / 25**: retention and PII-free logs close LLM02 on the data-at-rest side.
