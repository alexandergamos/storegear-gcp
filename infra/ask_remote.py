"""Ask the DEPLOYED agent (Agent Runtime) questions and time them, end to end from this laptop.

    uv run python infra/ask_remote.py "¿Cuánto cuesta el Polar Ignite 2 y hay stock?"
    uv run python infra/ask_remote.py --role manager "pregunta"

Each question uses a fresh managed session (Agent Platform Sessions) with the role in session state.
Error events from the runtime are printed (they arrive as events, not exceptions).
"""
import argparse
import json
import time
import warnings
from pathlib import Path

import vertexai

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / "infra" / "agent_runtime.json").read_text())


def ask(remote, question: str, role: str) -> float:
    session = remote.create_session(user_id="remote-test", state={"user:role": role})
    t0 = time.time()
    print(f"\n> [{role}] {question}")
    for ev in remote.stream_query(user_id="remote-test", session_id=session["id"], message=question):
        if ev.get("error_code"):
            print(f"  {time.time() - t0:5.1f}s ERROR  {ev['error_code']}: {ev.get('error_message', '')[:200]}")
        for p in (ev.get("content") or {}).get("parts", []) or []:
            if p.get("function_call"):
                print(f"  {time.time() - t0:5.1f}s CALL   {p['function_call']['name']}")
            elif p.get("text") and not p.get("thought"):
                print(f"  {time.time() - t0:5.1f}s ANSWER\n{p['text']}")
    took = time.time() - t0
    print(f"  total {took:.1f}s")
    return took


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="staff", choices=["staff", "manager"])
    ap.add_argument("questions", nargs="+")
    a = ap.parse_args()
    remote = vertexai.Client(project="storegear-prod-ag26", location=STATE["location"]).agent_engines.get(name=STATE["resource_name"])
    for q in a.questions:
        ask(remote, q, a.role)
