# Search filtered by watch model: design

- **Date:** 2026-10-27
- **Decided by:** Alexander (option 1 of 3). Drafted by Claude.
- **Applies to:** both agents (Google Cloud and n8n).

## Why
The catalog grows from 9 to 22 models on 2026-10-27, and many of the new names are close: Instinct 3 Solar / Instinct 3 AMOLED / Instinct E / Instinct Crossover AMOLED, and Forerunner 70 / 170 / 570 / 970. The search treats the model name as one more word, so a section from a similar watch can outrank the right one. When it does, the answer quotes another watch's specifications, for example a different battery figure. Leaving manuals out is not acceptable: they are different products with different specifications.

## Goals
- When a question names a catalog model, the search returns sections from that model's manual only. A comparison returns sections from each named model.
- When a question names something that fits several models (e.g. "Instinct 3"), the agent asks which one before answering.
- New manuals in Drive need no code or prompt change: the model list comes from the catalog.

## Non-goals and anti-goals
- **Non-goals:** no re-ingestion, no new chunk fields, no change to ranking (RRF), diversity or access control.
- **Anti-goal:** the model must never be guessed by an LLM. A question about the Instinct 3 Solar that searches only the AMOLED manual is worse than today.
- **Anti-goal:** when the filtered search finds nothing, it must not fall back to the unfiltered search. That would bring the wrong-model data back.

## Approaches considered
1. **Filter the search by model (chosen).** A deterministic resolver finds the catalog models named in the text, and the SQL search is restricted to their manuals. It is exact and testable, and it needs no re-ingestion. The cost is a change to both agents' search and a redeploy.
2. **Prefix every chunk with its model name and re-index.** It helps but stays probabilistic, and both catalogs have to be ingested again.
3. **Drop wrong-model results after searching.** It is simpler, but the agent is left with no data when the top results all belong to the wrong watch.

## Design

**Model registry.** It is built from the catalog's staff manuals (`SELECT DISTINCT file_name ...`, the query `/catalog/models` already runs) and cached for 10 minutes. Each manual gets:
- a **display name** from `api/catalog.display_name`, fixed for the new files: `vivoactive`, lower-case `fenix`, the `_UserGuide_EN` suffix and "Series";
- **match keys:** the display name with and without the brand, normalised (lower case, no accents, so `fēnix` = `fenix`; `-` and `_` read as spaces).

Manuals with the same display name are one model: Suunto Race 2 ES and EN.

**Resolver.** `resolve_models(text, registry)` returns the matched models and any ambiguous mentions.
- **Matching:** keys match as whole-word sequences, and the longest match wins. "Instinct 3 Solar" never also matches "Instinct 3", and "Forerunner 970" never matches "Forerunner 70".
- **Ambiguous:** a mention that is the start of two or more model names, with no full match (e.g. "instinct 3"), is returned as ambiguous, with the candidate models.
- **A partial name that fits a single model names nothing** (decided while building, 2026-10-27). Before the new manuals were in the catalog, "Instinct 3 Solar" partly matched the only Instinct 3 in it, the AMOLED. A filter to the AMOLED would have answered with the wrong watch's figures, so a partial name with one candidate searches unfiltered, as before.

**Search.** `hybrid_search(query, role, files=None)`:
- **Filter:** the `allowed` CTE gets `AND (:files IS NULL OR c.file_name = ANY(:files))`.
- **Polar:** when a Polar model is matched, the pseudo-manual "Polar · información común" is included as well.
- **No results:** a filtered search with no results returns no results.

**Agent (Google Cloud).**
- **Pre-retrieval and the tool share one helper.** It resolves the text, searches with the filter when one or more models match, and searches as today when none match. When the text is ambiguous, it does not search: it returns "Varios modelos encajan: X, Y. Pregunta al empleado a cuál se refiere". This works with rule 7 (ambiguity) as it stands.
- **The tool keeps its signature.** The agent is already told to put the full model name in every query, so follow-ups ("¿y la batería?") are filtered through the query text.
- **The prompt's hard-coded model list is removed.** The pre-retrieval block appends "MODELOS EN EL CATALOGO" from the registry, so the list follows Drive.

**n8n.** The same logic lives inside the Hybrid Search sub-workflow (`6PSmVXtajSeqL0Dl`), so the automatic pre-search and the tool both get it:
- a Postgres node reads the manual names;
- a Code node resolves the models (the same rules, ported to JavaScript);
- the SQL takes a fifth parameter, the list of files.

The model list in the n8n prompt (in Langfuse) is updated to the 22 models.

## Tests and proof
- **Resolver unit tests** use the real file names: Instinct 3 Solar / AMOLED / E / Crossover, Forerunner 70 / 170 / 570 / 970, Venu 4 / X1, fenix 8 with and without the accent, vivoactive 6, Race 2 ES+EN as one model, a comparison of two models, brand only ("Garmin": no filter), no model (no filter), and "Instinct 3" (ambiguous).
- **Search:** with `files` set, only those manuals come back; Polar adds the common manual.
- **Eval:**
  - the 22 questions on both agents must not drop;
  - a separate set of "similar models" questions, with answers taken from the manuals, must pass on both agents (it covers Instinct 3 Solar vs AMOLED battery, Forerunner 570 vs 970, Instinct E vs Crossover AMOLED, and one ambiguous "Instinct 3" question that must be answered with a question).

## Rollout
- **Google Cloud:** a PR (tests and CI), then Alexander's OK to merge. Alexander then redeploys the agent with `--min-instances 1` (the flag is needed, or the warm instance is lost) and sg-api through the normal workflow. The eval gate and the new set follow.
- **n8n:** the changes are made in the editor, either by Claude through the n8n connector once it is authorised, or by Alexander with the exact SQL and code. The n8n eval follows.

## Left to the builder
How the resolver code is organised, the cache, and the wording of the ambiguity message (Spanish, short).
