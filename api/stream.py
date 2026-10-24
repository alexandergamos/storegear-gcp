"""Both agents in parallel, blind (ADR-017): one event stream with slots A/B and no agent names.

n8n answers its webhook in one go, so its steps are simulated on a schedule while it works; its total time is
real. To keep the blind, both columns show the SAME three steps in the same order, without per-step times: the
real price/stock step and a guard block's short list would tell the agents apart (review C1). /chat/stream keeps
the real steps.
"""
import json
import queue
import random
import threading
import time
from typing import Callable, Iterator, Literal

from agents import CHECK, DRAFT, SEARCH

FAILED = "Este agente no ha podido responder ahora."
SLOT_TIMEOUT = 150   # seconds; past n8n's own 120 s, so a hung Agent Runtime call can't hold a column forever
BLIND_STEPS = [(label, status) for label in (CHECK, SEARCH, DRAFT) for status in ("running", "done")]


def n8n_schedule(rng=random) -> list[tuple[str, float]]:
    """Label, seconds from the start at which it shows as done; jittered so the timing isn't a fixed tell."""
    return [(CHECK, rng.uniform(0.6, 1.4)), (SEARCH, rng.uniform(2.2, 3.8))]


def n8n_events(ask: Callable[[], str], clock=time.monotonic,
               wait: Callable[[threading.Event, float], bool] | None = None,
               schedule: list[tuple[str, float]] | None = None) -> Iterator[dict]:
    """Simulated steps while `ask` runs in a thread; then answer {text} or error. A fast answer isn't held back."""
    wait = wait or (lambda ev, timeout: ev.wait(timeout))
    schedule = schedule or n8n_schedule()
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
    for label, until in schedule:
        yield {"type": "step", "label": label, "status": "running"}
        if not early:
            early = wait(finished, max(0.0, until - (clock() - t0)))
        yield {"type": "step", "label": label, "status": "done"}
    yield {"type": "step", "label": DRAFT, "status": "running"}
    finished.wait()
    yield {"type": "step", "label": DRAFT, "status": "done"}
    if "text" in box:
        yield {"type": "answer", "text": box["text"]}
    else:   # the reason is for the server log; merge_blind replaces it with the fixed text
        e = box["error"]
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"[:300]}


def merge_blind(slots: dict[Literal["A", "B"], Iterator[dict]], timeout: float = SLOT_TIMEOUT,
                clock=time.monotonic) -> Iterator[dict]:
    """Runs each slot in a thread and yields its events as they come, tagged with the slot.

    Steps: {type, slot, label, status}, always BLIND_STEPS in order for both slots (other labels are dropped,
    skipped ones are filled in, and an answer first completes the list). Exactly one terminal per slot: answer {type, slot, text, total_ms} (plus
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
    shown = {slot: 0 for slot in slots}   # how many of BLIND_STEPS each slot has shown

    def steps_up_to(slot, label, status):
        target = BLIND_STEPS.index((label, status)) + 1 if (label, status) in BLIND_STEPS else 0
        for lab, st in BLIND_STEPS[shown[slot]:target]:
            yield {"type": "step", "slot": slot, "label": lab, "status": st}
        shown[slot] = max(shown[slot], target)

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
            yield from steps_up_to(slot, e["label"], e["status"])
        elif e["type"] == "answer":
            yield from steps_up_to(slot, *BLIND_STEPS[-1])
            open_slots.discard(slot)
            extra = {k: v for k, v in e.items() if k == "session_id"}
            yield {"type": "answer", "slot": slot, "text": e["text"], "total_ms": total_ms(), **extra}
        else:
            yield error(slot)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
