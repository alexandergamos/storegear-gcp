"""Ask the StoreGear agent one or more questions from the terminal and see every step (tool calls, timing).

    uv run python agent/ask.py "¿Hasta qué profundidad es resistente al agua el Garmin Instinct 3 AMOLED?"
    uv run python agent/ask.py --role manager "¿Qué descuento máximo puede aplicar un encargado?"

Each question runs in a fresh session. Reads agent/storegear/.env like `adk web` does.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / "storegear" / ".env")
sys.path.insert(0, str(HERE))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from storegear.agent import root_agent  # noqa: E402


async def ask(question: str, role: str) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="storegear")
    session = await runner.session_service.create_session(app_name="storegear", user_id="cli", state={"user:role": role})
    t0 = time.time()
    msg = types.Content(role="user", parts=[types.Part(text=question)])
    print(f"\n> [{role}] {question}")
    async for ev in runner.run_async(user_id="cli", session_id=session.id, new_message=msg):
        for p in (ev.content.parts if ev.content else []) or []:
            if p.function_call:
                print(f"  {time.time() - t0:5.1f}s CALL   {p.function_call.name}({dict(p.function_call.args)})")
            elif p.function_response:
                print(f"  {time.time() - t0:5.1f}s RESULT {p.function_response.name} ({len(str(p.function_response.response))} chars)")
            elif p.text and not p.thought:
                print(f"  {time.time() - t0:5.1f}s ANSWER\n{p.text}")
    print(f"  total {time.time() - t0:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="staff", choices=["staff", "manager"])
    ap.add_argument("questions", nargs="+")
    a = ap.parse_args()
    for q in a.questions:
        asyncio.run(ask(q, a.role))
