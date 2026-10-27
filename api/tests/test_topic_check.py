"""The topic check runs on gemini-2.5-flash in europe-west1 with no thinking (ADR-015 addendum, 2026-10-27): 0.54 s median
against 2.5 s on gemini-3.8-flash (eu), still processed in the EU, one try, 8 s at most."""
import json
from types import SimpleNamespace

import guards


class FakeModels:
    def __init__(self, seen):
        self.seen = seen

    def generate_content(self, model, contents, config):
        self.seen.update(model=model, config=config)
        return SimpleNamespace(text=json.dumps({"on_topic": "paella" not in contents}))


def fake_client(monkeypatch):
    seen = {}

    def client(**kw):
        seen["client"] = kw
        return SimpleNamespace(models=FakeModels(seen))
    monkeypatch.setattr(guards, "_genai", None)
    monkeypatch.setattr(guards.genai, "Client", client)
    return seen


def test_the_topic_check_runs_on_the_light_model_in_europe_west1(monkeypatch):
    seen = fake_client(monkeypatch)
    assert guards.on_topic("¿Cuánto dura la batería del Venu 4?") is True
    assert seen["model"] == "gemini-2.5-flash"
    assert seen["client"]["location"] == "europe-west1" and seen["client"]["vertexai"] is True


def test_no_thinking_one_try_eight_seconds(monkeypatch):
    seen = fake_client(monkeypatch)
    guards.on_topic("Dame una receta de paella")
    cfg = seen["config"]
    assert cfg.thinking_config.thinking_budget == 0 and cfg.thinking_config.thinking_level is None
    assert cfg.http_options.timeout == 8000 and cfg.http_options.retry_options.attempts == 1
    assert cfg.temperature == 0


def test_an_off_topic_message_is_reported(monkeypatch):
    fake_client(monkeypatch)
    assert guards.on_topic("Dame una receta de paella") is False
