"""Ask the DEPLOYED agent (Agent Runtime) questions and time them, end to end from this laptop.

    uv run python infra/ask_remote.py "¿Cuánto cuesta el Polar Ignite 2 y hay stock?"
    uv run python infra/ask_remote.py --role manager "pregunta"

Each question uses a fresh managed session (Agent Platform Sessions) with the role in session state.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

import vertexai

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / "infra" / "agent_runtime.json").read_text())


async def ask(remote, question: str, role: str) -> float:
    session = await remote.async_create_session(user_id="remote-test", state={"user:role": role})
    t0 = time.time()
    print(f"\n> [{role}] {question}")
    async for ev in remote.async_stream_query(user_id="remote-test", session_id=session["id"], message=question):
        for p in (ev.get("content") or {}).get("parts", []) or []:
            if p.get("function_call"):
                print(f"  {time.time() - t0:5.1f}s CALL   {p['function_call']['name']}")
            elif p.get("text") and not p.get("thought"):
                print(f"  {time.time() - t0:5.1f}s ANSWER\n{p['text']}")
    took = time.time() - t0
    print(f"  total {took:.1f}s")
    return took


async def main(questions: list[str], role: str) -> None:
    client = vertexai.Client(project="storegear-prod-ag26", location=STATE["location"])
    remote = client.agent_engines.get(name=STATE["resource_name"])
    for q in questions:
        await ask(remote, q, role)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="staff", choices=["staff", "manager"])
    ap.add_argument("questions", nargs="+")
    a = ap.parse_args()
    asyncio.run(main(a.questions, a.role))
