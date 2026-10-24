"""Honest mode (2026-10-23): while Google restricts Agent Platform, the web demo talks to n8n alone, by name."""
import pytest

import agents
import main
from fakes import parse_sse


@pytest.fixture
def restricted(monkeypatch):
    monkeypatch.setattr(main, "GCP_STATUS", "restricted")


@pytest.fixture
def n8n(monkeypatch):
    calls = []

    def fake(message, uid, conversation_id, client=None):
        calls.append((message, uid, conversation_id))
        return "Respuesta de n8n."
    monkeypatch.setattr(agents, "ask_n8n", fake)
    return calls


def test_status_is_public(client, monkeypatch):
    assert client.get("/status").json() == {"gcp": "ok"}
    monkeypatch.setattr(main, "GCP_STATUS", "restricted")
    assert client.get("/status").json() == {"gcp": "restricted"}


def test_n8n_stream_only_in_honest_mode(client, as_user, no_rate_limit, n8n):
    as_user()
    assert client.post("/n8n/stream", json={"message": "hola"}).status_code == 404
    assert n8n == []


def test_n8n_stream_needs_a_token(client, restricted):
    assert client.post("/n8n/stream", json={"message": "hola"}).status_code == 401


def test_n8n_stream_answers_with_steps_without_times(client, as_user, no_rate_limit, restricted, n8n):
    as_user(uid="u1")
    out = parse_sse(client.post("/n8n/stream", json={"message": "¿Pesa mucho el Venu X1?"}).text)
    steps = [d for e, d in out if e == "step"]
    assert [d["label"] for d in steps if d["status"] == "done"] == ["Pregunta revisada", "Buscando en los manuales", "Redactando la respuesta"]
    assert all("ms" not in d for d in steps)   # n8n's steps are simulated: no invented per-step times
    event, data = out[-1]
    assert event == "answer" and data["text"] == "Respuesta de n8n." and isinstance(data["total_ms"], int)
    assert data["session_id"] == n8n[0][2]   # n8n's memory is keyed by this id: the follow-up reuses it
    assert no_rate_limit == ["u1"]


def test_n8n_stream_follow_up_keeps_the_conversation(client, as_user, no_rate_limit, restricted, n8n):
    as_user()
    client.post("/n8n/stream", json={"message": "hola", "session_id": "abc123"})
    assert n8n[0][2] == "abc123"


def test_n8n_stream_masks_pii(client, as_user, no_rate_limit, restricted, n8n):
    as_user()
    client.post("/n8n/stream", json={"message": "Soy ana@example.com"})
    assert n8n[0][0] == "Soy <EMAIL>"


def test_n8n_stream_failure_is_the_fixed_error(client, as_user, no_rate_limit, restricted, monkeypatch):
    as_user()

    def down(*a, **k):
        raise agents.AgentError("n8n status 500")
    monkeypatch.setattr(agents, "ask_n8n", down)
    event, data = parse_sse(client.post("/n8n/stream", json={"message": "hola"}).text)[-1]
    assert event == "error" and data["message"] == "Este agente no ha podido responder ahora."
