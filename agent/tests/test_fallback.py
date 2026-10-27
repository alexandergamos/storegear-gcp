"""Fallback model (decision 2026-10-27): when gemini-3.8-flash on `eu` is overloaded, the same call goes to
gemini-2.5-flash on europe-west1, which keeps processing in the EU (ADR-001)."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import errors, types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storegear.fallback import FallbackGemini  # noqa: E402

PRIMARY, BACKUP = "gemini-3.8-flash", "gemini-2.5-flash"


def server_error(code):
    return errors.ServerError(code, {"error": {"code": code, "message": "x", "status": "DEADLINE_EXCEEDED"}})


def client_error(code):
    return errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})


@pytest.fixture
def calls(monkeypatch):
    """Replaces the real API call: the primary model fails with calls["error"]; the backup answers."""
    seen = {"models": [], "thinking": [], "error": server_error(504), "fail_after_yield": False}

    async def fake(self, llm_request, stream=False):
        seen["models"].append(llm_request.model)
        seen["thinking"].append(llm_request.config.thinking_config)
        if llm_request.model == PRIMARY and seen["error"]:
            if seen["fail_after_yield"]:
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="parcial")]))
            raise seen["error"]
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=llm_request.model)]))

    monkeypatch.setattr(Gemini, "generate_content_async", fake)
    return seen


def run(model):
    req = LlmRequest(model=PRIMARY, config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low")))

    async def go():
        return [r.content.parts[0].text async for r in model.generate_content_async(req)]
    return asyncio.run(go())


def model():
    return FallbackGemini(model=PRIMARY, fallback=Gemini(model=BACKUP))


def test_a_504_on_the_primary_is_answered_by_the_backup(calls):
    assert run(model()) == [BACKUP]
    assert calls["models"] == [PRIMARY, BACKUP]


def test_the_backup_gets_a_thinking_budget_not_a_thinking_level(calls):
    # gemini-2.5 models reject thinking_level
    run(model())
    assert calls["thinking"][1].thinking_level is None and calls["thinking"][1].thinking_budget is not None


@pytest.mark.parametrize("error", [server_error(503), server_error(500), client_error(429),
                                   httpx.ReadTimeout("slow"), asyncio.TimeoutError()])
def test_overload_and_timeouts_fall_back(calls, error):
    calls["error"] = error
    assert run(model()) == [BACKUP]


def test_a_bad_request_is_not_hidden_by_the_backup(calls):
    calls["error"] = client_error(400)
    with pytest.raises(errors.ClientError):
        run(model())
    assert calls["models"] == [PRIMARY]


def test_a_healthy_primary_never_calls_the_backup(calls):
    calls["error"] = None
    assert run(model()) == [PRIMARY]
    assert calls["models"] == [PRIMARY]


def test_no_fallback_once_the_primary_has_answered_part_of_a_stream(calls):
    calls["fail_after_yield"] = True
    with pytest.raises(errors.ServerError):
        run(model())
    assert calls["models"] == [PRIMARY]


def test_without_a_backup_the_error_is_raised(calls):
    with pytest.raises(errors.ServerError):
        run(FallbackGemini(model=PRIMARY))


def run_with_timeout(model, timeout_ms=15000):
    req = LlmRequest(model=PRIMARY, config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low"), http_options=types.HttpOptions(timeout=timeout_ms)))

    async def go():
        return [r.content.parts[0].text async for r in model.generate_content_async(req)]
    return asyncio.run(go())


@pytest.fixture
def timeouts(monkeypatch):
    """Which per-call timeout each model was called with."""
    seen = []

    async def fake(self, llm_request, stream=False):
        seen.append((llm_request.model, llm_request.config.http_options.timeout))
        if llm_request.model == PRIMARY:
            raise server_error(504)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=llm_request.model)]))

    monkeypatch.setattr(Gemini, "generate_content_async", fake)
    return seen


def test_the_primary_gets_a_short_timeout_and_the_backup_a_long_one(timeouts):
    # 27 Oct: answered 3.8 Flash calls took a median 2.0 s (p90 3.6 s); waiting 12-15 s before switching only adds wait
    run_with_timeout(FallbackGemini(model=PRIMARY, fallback=Gemini(model=BACKUP), primary_timeout_ms=6000))
    assert timeouts == [(PRIMARY, 6000), (BACKUP, 15000)]


def test_without_a_primary_timeout_the_configured_one_is_kept(timeouts):
    run_with_timeout(FallbackGemini(model=PRIMARY, fallback=Gemini(model=BACKUP)), timeout_ms=9000)
    assert timeouts == [(PRIMARY, 9000), (BACKUP, 9000)]


def test_the_switch_is_logged_with_both_models(calls, caplog):
    # a print() never reached Agent Runtime's logs; the logger does
    with caplog.at_level("WARNING", logger="storegear"):
        run(model())
    assert any(PRIMARY in r.getMessage() and BACKUP in r.getMessage() for r in caplog.records)
