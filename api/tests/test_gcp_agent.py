"""gcp_events: today's /chat flow as a stream of steps, replayed against a fake Agent Runtime."""
import itertools

import pytest

import agents
import guards
import main
from fakes import PRICE_EVENTS, FakeRemote, ev

SEARCH, PRICE, DRAFT, CHECK = "Buscando en los manuales", "Consultando precio y stock", "Redactando la respuesta", "Pregunta revisada"


def clock():
    return itertools.count(0, 0.5).__next__   # every reading is 0.5 s after the last


def run(remote, message="¿Cuánto cuesta el Venu X1 y hay stock?", session_id=None):
    return list(agents.gcp_events(remote, "u1", "staff", message, session_id, clock=clock()))


def test_price_question_steps(clean_guards):
    out = run(FakeRemote(PRICE_EVENTS))
    steps = [e for e in out if e["type"] == "step"]
    assert [s["label"] for s in steps if s["status"] == "running"] == [CHECK, SEARCH, PRICE, DRAFT]
    assert [s["label"] for s in steps if s["status"] == "done"] == [CHECK, SEARCH, PRICE, DRAFT]
    for s in steps:
        assert ("ms" in s) == (s["status"] == "done")
        assert s.get("ms", 0) >= 0
    assert [e["type"] for e in out].count("answer") == 1
    assert out[-1]["type"] == "answer"
    assert out[-1]["text"] == "El Venu X1 cuesta 549 € y hay 3 en stock."
    assert out[-1]["session_id"] == "new-session"


def test_each_step_runs_before_it_is_done(clean_guards):
    out = [(e["label"], e["status"]) for e in run(FakeRemote(PRICE_EVENTS)) if e["type"] == "step"]
    for label in (CHECK, SEARCH, PRICE, DRAFT):
        assert out.index((label, "running")) < out.index((label, "done"))


def test_answer_without_tools_goes_search_then_draft(clean_guards):
    out = run(FakeRemote([ev({"text": "Se carga en 2 horas."})]))
    assert [e["label"] for e in out if e["type"] == "step" and e["status"] == "done"] == [CHECK, SEARCH, DRAFT]


def test_model_armor_hit_never_calls_agent(monkeypatch):
    monkeypatch.setattr(guards, "armor", lambda text, response=False: ["pi_and_jailbreak"])
    monkeypatch.setattr(guards, "on_topic", lambda text: pytest.fail("topic check must not run on blocked text"))
    remote = FakeRemote(PRICE_EVENTS)
    out = run(remote)
    assert remote.calls == []
    assert out[-1]["type"] == "answer"
    assert out[-1]["text"] == agents.REPLY["blocked"]
    assert out[-1]["guard"]["blocked"] == "input"


def test_off_topic_is_an_answer(monkeypatch):
    monkeypatch.setattr(guards, "armor", lambda text, response=False: [])
    monkeypatch.setattr(guards, "on_topic", lambda text: False)
    out = run(FakeRemote(PRICE_EVENTS))
    assert out[-1]["type"] == "answer" and out[-1]["text"] == agents.REPLY["off_topic"]


def test_runtime_error_without_text_is_an_error(clean_guards):
    out = run(FakeRemote([ev(error_code="UNAVAILABLE")]))
    assert out[-1]["type"] == "error"
    assert out[-1]["status"] == 502


def test_guardrail_down_is_an_error(monkeypatch):
    def down(text, response=False):
        raise RuntimeError("armor down")
    monkeypatch.setattr(guards, "armor", down)
    out = run(FakeRemote(PRICE_EVENTS))
    assert out[-1]["type"] == "error" and out[-1]["status"] == 503


def test_unknown_session_is_an_error(clean_guards):
    out = run(FakeRemote(PRICE_EVENTS), session_id="someone-elses")
    assert out[-1]["type"] == "error" and out[-1]["status"] == 404


def test_session_with_another_role_is_not_reused(clean_guards):
    remote = FakeRemote(PRICE_EVENTS, sessions={("u1", "s1"): {"state": {"user:role": "manager"}}})
    assert run(remote, session_id="s1")[-1]["session_id"] == "new-session"
    remote = FakeRemote(PRICE_EVENTS, sessions={("u1", "s1"): {"state": {"user:role": "staff"}}})
    assert run(remote, session_id="s1")[-1]["session_id"] == "s1"


def test_partial_events_only_when_enabled(clean_guards, monkeypatch):
    events = [ev({"text": "El Venu"}, partial=True), ev({"text": "El Venu X1 cuesta 549 €."})]
    remote = FakeRemote(events)
    assert run(remote)[-1]["text"] == "El Venu X1 cuesta 549 €."
    assert remote.calls[-1][4] == {}
    monkeypatch.setattr(agents, "PARTIAL_EVENTS", True)
    remote = FakeRemote(events)
    assert run(remote)[-1]["text"] == "El Venu X1 cuesta 549 €."
    assert remote.calls[-1][4] == {"run_config": {"streaming_mode": "sse"}}


# ---------------------------------------------------------------- /chat keeps its JSON contract
@pytest.fixture
def chat(client, as_user, no_rate_limit, monkeypatch):
    as_user()

    def _chat(events, **body):
        monkeypatch.setattr(main, "remote", lambda: FakeRemote(events))
        return client.post("/chat", json={"message": "¿Cuánto cuesta el Venu X1?", **body})
    return _chat


def test_chat_json_shape(chat, clean_guards):
    r = chat(PRICE_EVENTS)
    assert r.status_code == 200
    body = r.json()
    assert list(body) == ["session_id", "answer", "seconds", "guard"]
    assert body["session_id"] == "new-session"
    assert body["answer"] == "El Venu X1 cuesta 549 € y hay 3 en stock."
    assert isinstance(body["seconds"], float)
    assert body["guard"] == {"pii_in": [], "pii_out": [], "links_removed": 0}


def test_chat_blocked_shape(chat, monkeypatch):
    monkeypatch.setattr(guards, "armor", lambda text, response=False: ["sexually_explicit"])
    body = chat(PRICE_EVENTS, session_id="s9").json()
    assert body == {"session_id": "s9", "answer": main.REPLY["blocked"], "guard": {"pii_in": [], "blocked": "input", "filters": ["sexually_explicit"]}}


def test_chat_status_codes(chat, clean_guards, monkeypatch):
    assert chat([ev(error_code="UNAVAILABLE")]).status_code == 502
    assert chat(PRICE_EVENTS, session_id="nope").status_code == 404
    monkeypatch.setattr(guards, "armor", lambda text, response=False: (_ for _ in ()).throw(RuntimeError()))
    assert chat(PRICE_EVENTS).status_code == 503
