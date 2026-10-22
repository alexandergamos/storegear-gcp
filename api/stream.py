"""Both agents in parallel, blind (ADR-017): one event stream with slots A/B and no agent names.

n8n answers its webhook in one go, so its steps are simulated on a fixed schedule while it works; its total time
is real. Steps lose their per-step time here (n8n's would be invented and would give the blind away).
"""
import json
import queue
import threading
import time
from typing import Callable, Iterator, Literal

from agents import CHECK, DRAFT, SEARCH

FAILED = "Este agente no ha podido responder ahora."
SLOT_TIMEOUT = 150   # seconds; past n8n's own 120 s, so a hung Agent Runtime call can't hold a column forever
N8N_SCHEDULE = [(CHECK, 1.0), (SEARCH, 3.0)]   # label, seconds from the start at which it shows as done


def n8n_events(ask: Callable[[], str], clock=time.monotonic,
               wait: Callable[[threading.Event, float], bool] | None = None) -> Iterator[dict]:
    """Simulated steps while `ask` runs in a thread; then answer {text} or error. A fast answer isn't held back."""
    wait = wait or (lambda ev, timeout: ev.wait(timeout))
    finished, box = threading.Event(), {}

    def run():
        try:
            box["text"] = ask()
        except Exception as e:  # noqa: BLE001
            box["error"] = e
        finally:
            finished.set()

    t0 = clock()
    threading.Thread(target=run, daemon=True).start()
    early = False
    for label, until in N8N_SCHEDULE:
        yield {"type": "step", "label": label, "status": "running"}
        if not early:
            early = wait(finished, max(0.0, until - (clock() - t0)))
        yield {"type": "step", "label": label, "status": "done"}
    yield {"type": "step", "label": DRAFT, "status": "running"}
    finished.wait()
    yield {"type": "step", "label": DRAFT, "status": "done"}
    if "text" in box:
        yield {"type": "answer", "text": box["text"]}
    else:
        yield {"type": "error", "message": "n8n failed"}


def merge_blind(slots: dict[Literal["A", "B"], Iterator[dict]], timeout: float = SLOT_TIMEOUT,
                clock=time.monotonic) -> Iterator[dict]:
    """Runs each slot in a thread and yields its events as they come, tagged with the slot.

    Steps: {type, slot, label, status}. Exactly one terminal per slot: answer {type, slot, text, total_ms} (plus
    the agent's internal fields such as session_id, for the caller to keep or drop) or error {type, slot, message,
    total_ms} with a fixed message, whatever went wrong (exception, error event, no terminal, timeout).
    """
    q: queue.Queue = queue.Queue()
    END = object()

    def run(slot, it):
        try:
            for e in it:
                q.put((slot, e))
        except Exception:  # noqa: BLE001  the reason goes nowhere near the client
            q.put((slot, {"type": "error"}))
        q.put((slot, END))

    t0 = clock()
    for slot, it in slots.items():
        threading.Thread(target=run, args=(slot, it), daemon=True).start()
    open_slots = set(slots)

    def total_ms():
        return round((clock() - t0) * 1000)

    def error(slot):
        open_slots.discard(slot)
        return {"type": "error", "slot": slot, "message": FAILED, "total_ms": total_ms()}

    while open_slots:
        try:
            slot, e = q.get(timeout=max(0.0, timeout - (clock() - t0)))
        except queue.Empty:
            for slot in sorted(open_slots):
                yield error(slot)
            return
        if slot not in open_slots:
            continue   # after its terminal or its timeout: nothing more from this slot
        if e is END:
            yield error(slot)   # ended without an answer
        elif e["type"] == "step":
            yield {"type": "step", "slot": slot, "label": e["label"], "status": e["status"]}
        elif e["type"] == "answer":
            open_slots.discard(slot)
            extra = {k: v for k, v in e.items() if k == "session_id"}
            yield {"type": "answer", "slot": slot, "text": e["text"], "total_ms": total_ms(), **extra}
        else:
            yield error(slot)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
