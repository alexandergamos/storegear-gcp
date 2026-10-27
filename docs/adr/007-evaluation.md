# ADR-007 — Evaluation approach and Phase 1 gate

- **Status:** Accepted (2026-10-17)
- **Date:** 2026-10-17
- **Linear:** SMO-14
- **Deciders:** Alexander (decides) · Claude (drafts)

## Context
ADR-000's quality bar: on the 22-question eval, each metric ≥ the n8n baseline minus 0.1 (Correctness 5.00, Faithfulness 4.95, Context relevance 5.00, Answer relevance 5.00; median latency 9.0 s). n8n ran it in its native *Evaluations* tab, with judge prompts in Langfuse and Gemini 3.8 Flash as the judge.

## Options considered
| Option | Pros | Cons |
|---|---|---|
| **Own harness (`eval/run_eval.py`) replicating n8n exactly** | Same dataset, same judge prompts, same judge model → a fair comparison; also records latency, searches and tokens; runs from the CLI and in CI later | Code to maintain |
| `adk eval` | Native to ADK; evalset format | Different scoring (trajectory and response match), so it's not comparable to the n8n numbers |
| Agent Platform Agent Evaluation (autoraters, simulated users) | Managed; multi-turn; live-traffic scoring | Different rubric and scale, so it's not comparable to the baseline; better as a second layer after deploy |
| Ragas / DeepEval | Popular RAG metrics | Third-party; different definitions |

## Decision
- **The harness replicates n8n:** dataset `eval/dataset.json` (22 questions, exported from the n8n data table). The judge prompts `eval/judges/correctness.md` and `rag_triad.md` are copied verbatim from Langfuse (label staging). Judge: `gemini-3.8-flash`, temperature 0, structured JSON. The judge sees exactly what the agent saw (pre-retrieval plus every extra search). Each question runs in a fresh session, role staff, as `sg-agent`.
- **The gate:** a change ships only if every metric is ≥ baseline − 0.1. Results are saved in `eval/results/` (git-ignored); the summaries are recorded here.
- Agent Platform Agent Evaluation is kept for after deploy (SMO-25: live traffic, multi-turn).

## Results (2026-10-17)
| Run | Change | Corr | Faith | Ctx | Ans | Median | Notes |
|---|---|---|---|---|---|---|---|
| 1 | n8n prompt as is, thinking low | 4.77 ❌ | 4.95 | 5.00 | 5.00 | 4.8 s | Q6 (missed the 30 m spec), Q12/Q13 (didn't explain how to open the menu): the agent stopped one search early |
| 2 | thinking **medium** (Q6/12/13 only) | — | — | — | — | 29 s | Fixes the how-to questions; 6× slower, 2.5× tokens → **rejected** |
| 3 | low + **explicit guidance** + **timeout/retry** | **4.95** ✅ | **4.91** ✅ | **5.00** ✅ | **5.00** ✅ | **6.2 s** ✅ | Remaining <5: Q9 F4 (as in n8n), Q13 C4/F4 |

**Gate: passed.** About 9,900 input / 130 output tokens per answer.

## What changed to pass
1. **Pre-retrieval guidance** (our block; the n8n system prompt itself is untouched) gained two explicit cases: how-to answers that name a menu must search how to open it; spec figures missing from the results must trigger a search for "<model> especificaciones tecnicas <dato>".
2. **Tail-latency guard:** the `eu` endpoint has a ~2.5 s median per model call but occasional 30–190 s queueing (measured: `global` stayed under 4.4 s in the same sample). Each call now has a 15 s deadline and up to 3 attempts. The server answers 504, the SDK retries, and slow calls usually land on free capacity. Worst case is about 48 s and then a clean error (handled by the dead-letter queue in Phase 4).

## Addendum (2026-10-18, SMO-15): eval against the deployed agent
| Run | Corr | Faith | Ctx | Ans | Median |
|---|---|---|---|---|---|
| 4 · **cloud (Agent Runtime eu)** | 4.86 | 5.00 | 4.95 | 5.00 | **3.0 s** |

Correctness misses the gate by 0.04, from **Q6 only** (Ignite 2 water resistance, scoring between 3 and 5 across runs).
**Root cause:** the "30 m" lives in one row of the specs **HTML table** (`<td>Impermeabilidad:</td><td>30 m (ISO 22810…`), chunked together with a long GPS-accuracy paragraph. Vector search sees "GPS accuracy", and keyword search prefers the boilerplate section *"La impermeabilidad al agua de los productos Polar"*, which repeats in every Polar manual (9 of the 15 slots returned for Q6).
**Decision (Alexander, option A):** close Phase 1 with this documented gap. Fix the cause in **SMO-17** (table-aware chunking: one chunk per spec row with its product header; de-duplicate cross-manual boilerplate), then re-run the gate in the cloud. No hand patch to the data now.

## Addendum (2026-10-18, SMO-17): eval on the new catalog, in the cloud
| Run | Corr | Faith | Ctx | Ans | Median | Notes |
|---|---|---|---|---|---|---|
| 5 · cloud, catalog v2 | 4.82 | 4.82 | 5.00 | 4.82 | **3.8 s** | 21/22 perfect; **Q6 now 5**; Q9 = 504 DEADLINE_EXCEEDED after 40 s (all 3 attempts of 15 s timed out) |
| 5b · Q9 re-run | 5 | 5 | 5 | 5 | 2.5 s | Same question, normal answer |

**Quality: 22/22 answers at 5 when the model responds.** The remaining risk is **availability**: the `eu` endpoint's tail latency can still outlast 3 × 15 s. Handled in Phase 4 (SMO-27): a friendly fallback reply, the dead-letter queue, and possibly a smarter retry policy (longer last attempt, or a non-EU fallback only with Alexander's approval).

**Update (2026-10-27, SMO-27):** handled with a fixed friendly reply, an email alert at 3 failed answers in an hour, and a backup model that stays in the EU: one attempt on `gemini-3.8-flash` (`eu`), then `gemini-2.5-flash` in europe-west1 (ADR-001 addendum). No non-EU fallback. Failed answers are not queued for a retry: each one is logged with its reason, never the question.

## Consequences
- **Good:** quality parity with n8n and 30 % faster median. A repeatable, scripted gate is ready for CI (SMO-28).
- **Bad / accepted:** the guidance deviates slightly from n8n's text, recorded here. LLM judges have variance: one question can move ±1 between runs. n8n duplicated Q10/Q16 (as Q21/Q22) for that reason.
- **Caveats:** the judges use the same model family as the agent (self-preference bias is possible). The 22 questions are a small sample, so this is a regression gate, not a statistical proof.

## Revisit when
- Real usage patterns differ from the 22 questions: add cases from production traces.
- The `eu` tail latency persists in production: consider Provisioned Throughput, or `global` for non-personal traffic (a residency trade-off for Alexander to decide).

## Learn more
- LLM-as-a-judge pitfalls: https://arxiv.org/abs/2306.05685
- Agent evaluation on Agent Platform: https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation
