import json
import threading

import stream

FAILED = "Este agente no ha podido responder ahora."


def gated(events, gate: threading.Event | None = None):
    """Yields the events; waits for `gate` before the last one (a slow agent)."""
    for i, e in enumerate(events):
        if gate and i == len(events) - 1:
            gate.wait(5)
        yield e


STEP = {"type": "step", "label": "Buscando en los manuales", "status": "done", "ms": 812}
ANSWER = {"type": "answer", "text": "Respuesta.", "session_id": "s1", "guard": {}, "seconds": 1.0}


def test_slow_slot_does_not_delay_fast_slot():
    gate = threading.Event()
    out = stream.merge_blind({"A": gated([STEP, ANSWER], gate), "B": gated([STEP, ANSWER])})
    seen = []
    for e in out:
        seen.append((e["slot"], e["type"]))
        if (e["slot"], e["type"]) == ("B", "answer"):
            gate.set()   # A only finishes after B's answer was already delivered
    assert seen.index(("B", "answer")) < seen.index(("A", "answer"))


def test_terminals_carry_total_ms_and_steps_drop_ms():
    out = list(stream.merge_blind({"A": iter([STEP, ANSWER]), "B": iter([STEP, ANSWER])}))
    steps = [e for e in out if e["type"] == "step"]
    assert steps and all(set(e) == {"type", "slot", "label", "status"} for e in steps)
    answers = [e for e in out if e["type"] == "answer"]
    assert {e["slot"] for e in answers} == {"A", "B"}
    assert all(isinstance(e["total_ms"], int) and e["text"] == "Respuesta." for e in answers)


def test_raising_slot_becomes_fixed_error():
    def broken():
        yield STEP
        raise RuntimeError("Agent Runtime 504 from gcp")

    out = list(stream.merge_blind({"A": broken(), "B": iter([ANSWER])}))
    err = [e for e in out if e["type"] == "error"]
    assert err == [{"type": "error", "slot": "A", "message": FAILED, "total_ms": err[0]["total_ms"]}]


def test_agent_error_terminal_becomes_fixed_error():
    out = list(stream.merge_blind({"A": iter([{"type": "error", "status": 502, "message": "agent error: x"}]), "B": iter([ANSWER])}))
    assert [e["message"] for e in out if e["type"] == "error"] == [FAILED]


def test_slot_without_terminal_is_an_error():
    out = list(stream.merge_blind({"A": iter([STEP]), "B": iter([ANSWER])}))
    assert [(e["slot"], e["message"]) for e in out if e["type"] == "error"] == [("A", FAILED)]


def test_hanging_slot_times_out_and_later_events_are_dropped():
    gate = threading.Event()
    out = list(stream.merge_blind({"A": gated([STEP, ANSWER], gate), "B": iter([ANSWER])}, timeout=0.2))
    gate.set()
    assert [(e["slot"], e["type"]) for e in out if e["type"] in ("answer", "error")] == [("B", "answer"), ("A", "error")]


def test_no_agent_names_or_step_times_in_events():
    gcp = iter([STEP, {**ANSWER, "guard": {"blocked": "off_topic"}}])
    n8n = stream.n8n_events(lambda: "Respuesta.", wait=lambda ev, t: ev.wait(0))
    for e in stream.merge_blind({"A": gcp, "B": n8n}):
        assert "ms" not in e
        text = json.dumps({k: v for k, v in e.items() if k != "text"})
        assert "gcp" not in text and "n8n" not in text and "Google" not in text


def test_sse_round_trips_spanish():
    s = stream.sse("answer", {"text": "¿Qué reloj? Cañón"})
    assert s.startswith("event: answer\ndata: ") and s.endswith("\n\n")
    assert json.loads(s.split("data: ", 1)[1]) == {"text": "¿Qué reloj? Cañón"}
    assert "¿Qué reloj? Cañón" in s


def test_n8n_events_schedule():
    waits = []
    out = list(stream.n8n_events(lambda: "ok", clock=lambda: 0.0, schedule=[("Pregunta revisada", 1.0), ("Buscando en los manuales", 3.0)],
                                 wait=lambda ev, t: waits.append(round(t, 2)) and False))
    steps = [(e["label"], e["status"]) for e in out if e["type"] == "step"]
    assert steps == [("Pregunta revisada", "running"), ("Pregunta revisada", "done"),
                     ("Buscando en los manuales", "running"), ("Buscando en los manuales", "done"),
                     ("Redactando la respuesta", "running"), ("Redactando la respuesta", "done")]
    assert waits == [1.0, 3.0]   # deadlines from the start: done at 1.0 s and 3.0 s while n8n works
    assert out[-1] == {"type": "answer", "text": "ok"}


def test_n8n_events_failure():
    def ask():
        raise RuntimeError("n8n status 500")

    out = list(stream.n8n_events(ask, wait=lambda ev, t: ev.wait(0)))
    assert out[-1]["type"] == "error"


def test_n8n_fast_answer_is_not_held_back():
    out = list(stream.n8n_events(lambda: "rápida"))   # real wait: returns as soon as the answer is there
    assert out[-1] == {"type": "answer", "text": "rápida"}


def test_n8n_default_schedule_is_jittered():
    for _ in range(20):
        (l1, t1), (l2, t2) = stream.n8n_schedule()
        assert (l1, l2) == ("Pregunta revisada", "Buscando en los manuales")
        assert 0.6 <= t1 <= 1.4 and 2.2 <= t2 <= 3.8
