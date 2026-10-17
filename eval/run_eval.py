"""SMO-14 · The 22-question eval: same dataset, same judges, same model as the n8n baseline.

    uv run python eval/run_eval.py                 # all 22 questions
    uv run python eval/run_eval.py --only 16 18    # a subset while iterating

For each question (fresh session, role staff, run AS sg-agent via agent/storegear/.env):
  1. run the agent; record answer, searches (pre-retrieval + tool calls), retrieved context, latency, tokens;
  2. Correctness judge (eval/judges/correctness.md + expected vs actual answer) -> score 1-5;
  3. RAG-triad judge (eval/judges/rag_triad.md) -> faithfulness, context relevance, answer relevance 1-5.
Judges: gemini-3.8-flash, temperature 0, structured JSON output (as in n8n).
Writes eval/results/<timestamp>.json (git-ignored) and prints a comparison with the n8n baseline.

Baseline (n8n, 2026-10-11): Correctness 5.00 · Faithfulness 4.95 · Context 5.00 · Answer 5.00 · median 9.0 s.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "agent" / "storegear" / ".env")
sys.path.insert(0, str(ROOT / "agent"))

from google import genai  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from storegear import agent as sg  # noqa: E402

BASELINE = {"correctness": 5.00, "faithfulness": 4.95, "context_relevance": 5.00, "answer_relevance": 5.00, "median_s": 9.0}
JUDGE_MODEL = "gemini-3.8-flash"
judge = genai.Client(vertexai=True, project="storegear-prod-ag26", location="eu")

CORRECTNESS_SCHEMA = {"type": "object", "properties": {
    "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reasoning": {"type": "string"}},
    "required": ["score", "reasoning"]}
TRIAD_SCHEMA = {"type": "object", "properties": {
    "faithfulness": {"type": "integer", "minimum": 1, "maximum": 5},
    "context_relevance": {"type": "integer", "minimum": 1, "maximum": 5},
    "answer_relevance": {"type": "integer", "minimum": 1, "maximum": 5},
    "reason": {"type": "string"}},
    "required": ["faithfulness", "context_relevance", "answer_relevance", "reason"]}


def load_prompt(name: str) -> str:
    text = (ROOT / "eval" / "judges" / name).read_text(encoding="utf-8")
    if text.startswith("PASTE HERE"):
        sys.exit(f"eval/judges/{name} still has the placeholder: paste the Langfuse prompt first")
    return text


def ask_judge(prompt: str, schema: dict) -> dict:
    for attempt in range(4):
        try:
            r = judge.models.generate_content(
                model=JUDGE_MODEL, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json", response_schema=schema))
            return json.loads(r.text)
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                return {"error": str(e)[:200]}
            time.sleep(2 ** attempt)


async def run_agent(question: str) -> dict:
    runner = InMemoryRunner(agent=sg.root_agent, app_name="storegear")
    session = await runner.session_service.create_session(app_name="storegear", user_id="eval", state={"user:role": "staff"})
    t0 = time.time()
    answer, searches, calls, tokens_in, tokens_out, inv = "", [], 0, 0, 0, None
    msg = types.Content(role="user", parts=[types.Part(text=question)])
    async for ev in runner.run_async(user_id="eval", session_id=session.id, new_message=msg):
        inv = inv or ev.invocation_id
        if ev.usage_metadata:
            tokens_in += ev.usage_metadata.prompt_token_count or 0
            tokens_out += (ev.usage_metadata.candidates_token_count or 0) + (ev.usage_metadata.thoughts_token_count or 0)
        for p in (ev.content.parts if ev.content else []) or []:
            if p.function_call:
                calls += 1
            if p.function_response and p.function_response.name == "buscar_catalogo_hibrido":
                searches.append(str(p.function_response.response.get("result", p.function_response.response)))
            if p.text and not p.thought and ev.author == "storegear":
                answer += p.text
    pre = sg.LAST_PRE.get(inv, "")
    return {"answer": answer.strip(), "latency_s": round(time.time() - t0, 2), "tool_calls": calls,
            "extra_searches": len(searches), "pre_retrieval": pre, "searches": searches,
            "tokens_in": tokens_in, "tokens_out": tokens_out}


def build_context(run: dict, question: str) -> str:
    parts = []
    if run["pre_retrieval"]:
        parts.append(f"### Busqueda previa (automatica): {json.dumps(question, ensure_ascii=False)}\n{run['pre_retrieval']}")
    parts += [f"### Busqueda {i + 1}:\n{s}" for i, s in enumerate(run["searches"])]
    return "\n\n".join(parts)[:80000] or "(vacio: el asistente no hizo ninguna busqueda)"


def main(only: list[int]) -> None:
    corr_prompt, triad_prompt = load_prompt("correctness.md"), load_prompt("rag_triad.md")
    qs = json.load(open(ROOT / "eval" / "dataset.json", encoding="utf-8"))
    if only:
        qs = [q for q in qs if q["qid"] in only]
    results = []
    for q in qs:
        run = asyncio.run(run_agent(q["question"]))
        fill = lambda t: t.replace("{{question}}", q["question"]).replace("{{category}}", q["category"])  # noqa: E731
        corr = ask_judge(fill(corr_prompt) + f"\n\nRespuesta esperada:\n{q['expected_answer']}\n\nRespuesta real:\n{run['answer']}", CORRECTNESS_SCHEMA)
        ctx = build_context(run, q["question"])
        triad = ask_judge(fill(triad_prompt).replace("{{context}}", ctx).replace("{{answer}}", run["answer"]), TRIAD_SCHEMA)
        row = {"qid": q["qid"], "category": q["category"], "question": q["question"], **run,
               "correctness": corr.get("score"), "correctness_reason": corr.get("reasoning", corr.get("error")),
               "faithfulness": triad.get("faithfulness"), "context_relevance": triad.get("context_relevance"),
               "answer_relevance": triad.get("answer_relevance"), "triad_reason": triad.get("reason", triad.get("error"))}
        results.append(row)
        print(f"Q{q['qid']:<3} C{row['correctness']} F{row['faithfulness']} X{row['context_relevance']} A{row['answer_relevance']} "
              f"{run['latency_s']:5.1f}s searches+{run['extra_searches']}  {q['category']}")

    mean = lambda k: round(statistics.mean(r[k] for r in results if isinstance(r[k], int)), 2)  # noqa: E731
    summary = {"correctness": mean("correctness"), "faithfulness": mean("faithfulness"),
               "context_relevance": mean("context_relevance"), "answer_relevance": mean("answer_relevance"),
               "median_s": round(statistics.median(r["latency_s"] for r in results), 1),
               "tokens_in_avg": round(statistics.mean(r["tokens_in"] for r in results)),
               "tokens_out_avg": round(statistics.mean(r["tokens_out"] for r in results)), "n": len(results)}
    print("\n             Google Cloud   n8n baseline")
    for k in ("correctness", "faithfulness", "context_relevance", "answer_relevance", "median_s"):
        print(f"  {k:18} {summary[k]:>6}        {BASELINE[k]}")
    print(f"  tokens per answer: {summary['tokens_in_avg']} in / {summary['tokens_out_avg']} out")
    low = [r for r in results if any(isinstance(r[k], int) and r[k] < 5 for k in ("correctness", "faithfulness", "context_relevance", "answer_relevance"))]
    for r in low:
        print(f"  <5 Q{r['qid']}: {r['correctness_reason'][:140] if r['correctness'] != 5 else r['triad_reason'][:140]}")
    out = ROOT / "eval" / "results" / f"{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    json.dump({"summary": summary, "results": results}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nsaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, nargs="*", default=[])
    main(ap.parse_args().only)
