"""POST /chat/stream: the Google Cloud agent alone, with real per-step times."""
import pytest

import main
from fakes import PRICE_EVENTS, FakeRemote, ev, parse_sse


@pytest.fixture
def remote(monkeypatch):
    r = FakeRemote(PRICE_EVENTS)
    monkeypatch.setattr(main, "remote", lambda: r)
    return r


def post(client, message="¿Cuánto cuesta el Venu X1?", **body):
    return client.post("/chat/stream", json={"message": message, **body})


def test_steps_have_times_and_answer_has_total(client, as_user, no_rate_limit, clean_guards, remote):
    as_user()
    r = post(client)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    out = parse_sse(r.text)
    steps = [d for e, d in out if e == "step"]
    assert [d["label"] for d in steps if d["status"] == "done"] == [
        "Pregunta revisada", "Buscando en los manuales", "Consultando precio y stock", "Redactando la respuesta"]
    assert all(isinstance(d["ms"], int) for d in steps if d["status"] == "done")
    assert all("ms" not in d for d in steps if d["status"] == "running")
    assert out[-1][0] == "answer"
    assert set(out[-1][1]) == {"text", "total_ms", "session_id"}
    assert out[-1][1]["session_id"] == "new-session"


def test_needs_token(client):
    assert post(client).status_code == 401


def test_any_role_no_demo_needed(client, as_user, no_rate_limit, clean_guards, remote):
    as_user(role="manager", demo=False)
    assert parse_sse(post(client).text)[-1][0] == "answer"


def test_one_rate_limit_call(client, as_user, no_rate_limit, clean_guards, remote):
    as_user()
    post(client)
    assert no_rate_limit == ["u1"]


def test_message_masked(client, as_user, no_rate_limit, clean_guards, remote):
    as_user()
    post(client, "Llamadme al 612 345 678, ¿stock del Venu X1?")
    assert [c[3] for c in remote.calls if c[0] == "stream_query"] == ["Llamadme al <TELEFONO>, ¿stock del Venu X1?"]


def test_agent_failure_is_an_error_event(client, as_user, no_rate_limit, clean_guards, monkeypatch):
    as_user()
    monkeypatch.setattr(main, "remote", lambda: FakeRemote([ev(error_code="UNAVAILABLE")]))
    out = parse_sse(post(client).text)
    assert out[-1][0] == "error"
    assert out[-1][1]["message"] == "Este agente no ha podido responder ahora."
    assert isinstance(out[-1][1]["total_ms"], int)


def test_unreachable_google_is_an_error_event(client, as_user, no_rate_limit, clean_guards, monkeypatch):
    as_user()

    def blocked():
        raise RuntimeError("403 Forbidden")
    monkeypatch.setattr(main, "remote", blocked)
    assert parse_sse(post(client).text)[-1][0] == "error"
