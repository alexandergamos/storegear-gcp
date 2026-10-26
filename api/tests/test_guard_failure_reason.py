"""When a guardrail is unavailable the client gets the same fixed error, and our log says which guard failed and how:
the guard and the error kind (with its HTTP code), never the question."""
import itertools
import json
import logging

import requests

import agents
import guards
import main
from fakes import PRICE_EVENTS, FakeRemote

QUESTION = "¿Cuánto cuesta el Venu X1 y hay stock?"


def run(remote):
    clock = itertools.count(0, 0.5).__next__
    return list(agents.gcp_events(lambda: remote, "u1", "staff", QUESTION, None, clock=clock))


def http_error(code):
    r = requests.Response()
    r.status_code = code
    return requests.HTTPError(response=r)


def test_model_armor_down_names_the_guard_and_the_http_code(monkeypatch):
    def down(text, response=False):
        raise http_error(403)
    monkeypatch.setattr(guards, "armor", down)
    end = run(FakeRemote(PRICE_EVENTS))[-1]
    assert (end["type"], end["status"], end["message"]) == ("error", 503, "guardrail unavailable")
    assert end["reason"] == "armor_in: HTTPError 403"


def test_topic_check_down_names_the_guard(monkeypatch):
    monkeypatch.setattr(guards, "armor", lambda text, response=False: [])
    def slow(text):
        raise TimeoutError()
    monkeypatch.setattr(guards, "on_topic", slow)
    end = run(FakeRemote(PRICE_EVENTS))[-1]
    assert end["message"] == "guardrail unavailable" and end["reason"] == "topic_check: TimeoutError"


def test_output_armor_down_names_the_guard(monkeypatch):
    monkeypatch.setattr(guards, "on_topic", lambda text: True)
    def out_down(text, response=False):
        if response:
            raise RuntimeError("down")
        return []
    monkeypatch.setattr(guards, "armor", out_down)
    end = run(FakeRemote(PRICE_EVENTS))[-1]
    assert end["message"] == "guardrail unavailable" and end["reason"] == "armor_out: RuntimeError"


def test_the_failure_log_carries_the_reason_but_never_the_question(monkeypatch, caplog):
    def down(text, response=False):
        raise http_error(504)
    monkeypatch.setattr(guards, "armor", down)
    with caplog.at_level(logging.WARNING, logger="sg-api"):
        list(main.watched("gcp", run(FakeRemote(PRICE_EVENTS)), "u1", None))
    [line] = [json.loads(r.getMessage()) for r in caplog.records if r.name == "sg-api"]
    assert line["event"] == "AGENT_FAILED" and line["reason"] == "guardrail unavailable (armor_in: HTTPError 504)"
    assert "Venu" not in json.dumps(line)
