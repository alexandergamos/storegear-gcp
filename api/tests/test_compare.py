"""POST /compare against fake agents and the in-memory store."""
import pytest

import agents
import main
from fakes import FakeRemote, ev, parse_sse
from store import MemoryStore

GCP_TEXT, N8N_TEXT = "Respuesta del primero.", "Respuesta del segundo."


class FixedRng:
    def __init__(self, pick):
        self.pick = pick

    def choice(self, options):
        assert sorted(options) == ["gcp", "n8n"]
        return self.pick


@pytest.fixture
def setup(client, as_user, no_rate_limit, clean_guards, monkeypatch):
    store = MemoryStore()
    main.app.dependency_overrides[main.get_store] = lambda: store
    monkeypatch.setattr(main, "RNG", FixedRng("gcp"))
    remote = FakeRemote([ev({"text": GCP_TEXT})])
    monkeypatch.setattr(main, "remote", lambda: remote)
    n8n_calls = []

    def fake_n8n(message, uid, conversation_id, client=None):
        n8n_calls.append((message, uid, conversation_id))
        return N8N_TEXT
    monkeypatch.setattr(agents, "ask_n8n", fake_n8n)
    as_user(demo=True)

    class S:
        pass
    s = S()
    s.client, s.store, s.remote, s.n8n_calls, s.rate = client, store, remote, n8n_calls, no_rate_limit
    s.post = lambda **body: client.post("/compare", json={"message": "¿Cuánto pesa el Venu X1?", **body})
    return s


def events(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    return parse_sse(r.text)


def test_stream_shape_and_slots(setup):
    out = events(setup.post())
    assert out[0][0] == "conversation"
    answers = {d["slot"]: d["text"] for e, d in out if e == "answer"}
    assert answers == {"A": GCP_TEXT, "B": N8N_TEXT}   # mapping_a = gcp, so B is n8n
    assert out[-1][0] == "done" and out[-1][1]["votable"] is True
    assert all(set(d) == {"slot", "label", "status"} for e, d in out if e == "step")
    assert all(set(d) == {"slot", "text", "total_ms"} for e, d in out if e == "answer")


def test_mapping_b_gets_the_other_agent(setup, monkeypatch):
    monkeypatch.setattr(main, "RNG", FixedRng("n8n"))
    answers = {d["slot"]: d["text"] for e, d in events(setup.post()) if e == "answer"}
    assert answers == {"A": N8N_TEXT, "B": GCP_TEXT}


def test_no_agent_names_on_the_wire(setup):
    body = setup.post().text
    for word in ("gcp", "n8n", "Google", "new-session"):
        assert word not in body


def test_one_rate_limit_call(setup):
    setup.post()
    assert setup.rate == ["u1"]


def test_follow_up_reuses_gcp_session(setup):
    cid = events(setup.post())[0][1]["conversation_id"]
    assert setup.store.get_conversation(cid, "u1").gcp_session_id == "new-session"
    events(setup.post(conversation_id=cid))
    queries = [c for c in setup.remote.calls if c[0] == "stream_query"]
    assert [q[2] for q in queries] == ["new-session", "new-session"]
    assert [c[2] for c in setup.n8n_calls] == [cid, cid]   # n8n's conversationId is the conversation id


def test_other_users_conversation_is_404(setup, as_user):
    cid = events(setup.post())[0][1]["conversation_id"]
    as_user(uid="u2", demo=True)
    assert setup.post(conversation_id=cid).status_code == 404
    assert setup.post(conversation_id="unknown").status_code == 404


def test_revealed_conversation_is_closed(setup):
    cid = events(setup.post())[0][1]["conversation_id"]
    setup.store.reveal(cid, "u1")
    calls_before = (len(setup.remote.calls), len(setup.n8n_calls))
    r = setup.post(conversation_id=cid)
    assert r.status_code == 409 and r.json() == {"detail": "conversation closed"}
    assert (len(setup.remote.calls), len(setup.n8n_calls)) == calls_before


def test_message_is_masked_for_both_agents(setup):
    events(setup.client.post("/compare", json={"message": "Soy ana@example.com, ¿precio del Venu X1?"}))
    assert setup.n8n_calls[0][0] == "Soy <EMAIL>, ¿precio del Venu X1?"
    assert [c[3] for c in setup.remote.calls if c[0] == "stream_query"] == ["Soy <EMAIL>, ¿precio del Venu X1?"]


def test_failed_slot_is_not_votable(setup, monkeypatch):
    def down(*a, **k):
        raise agents.AgentError("n8n status 500")
    monkeypatch.setattr(agents, "ask_n8n", down)
    out = events(setup.post())
    assert [(d["slot"], d["message"]) for e, d in out if e == "error"] == [("B", "Este agente no ha podido responder ahora.")]
    assert out[-1][1]["votable"] is False


def test_unreachable_google_is_a_slot_error_not_a_500(setup, monkeypatch):
    def blocked():
        raise RuntimeError("403 Forbidden")
    monkeypatch.setattr(main, "remote", blocked)
    out = events(setup.post())
    assert [d["slot"] for e, d in out if e == "error"] == ["A"]
    assert [d["slot"] for e, d in out if e == "answer"] == ["B"]


def test_comparison_row_has_both_totals(setup):
    out = events(setup.post())
    k = out[-1][1]["comparison_id"]
    row = setup.store.comparisons[k]
    assert isinstance(row["a_total_ms"], int) and isinstance(row["b_total_ms"], int)
    assert (row["a_error"], row["b_error"]) == (False, False)
    assert row["question"] == "¿Cuánto pesa el Venu X1?"
