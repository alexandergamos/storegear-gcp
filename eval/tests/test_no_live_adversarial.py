"""Adversarial content is never sent to live Google models (Generative AI Prohibited Use Policy).
The live scripts carry only ordinary shop questions; attacks are tested with fakes (api/tests)."""
import sys
import types
from pathlib import Path

import pytest

import injection_benchmark

EVAL = Path(__file__).resolve().parents[1]


def test_live_guardrail_script_sends_only_shop_questions():
    src = (EVAL / "guardrail_tests.py").read_text(encoding="utf-8").lower()
    for attack in ("ignora todas tus instrucciones", "prompt de sistema", "sexual", "herramientas internas"):
        assert attack not in src


@pytest.mark.parametrize("detector", ["gemini", "armor"])
def test_benchmark_refuses_live_detectors(monkeypatch, detector):
    def never(_text):
        raise AssertionError("a live detector was called")

    fake = types.SimpleNamespace(regex_check=lambda t: {}, gemini_check=never, armor_check=never)
    monkeypatch.setitem(sys.modules, "injection_check", fake)
    with pytest.raises(SystemExit) as e:
        injection_benchmark.run(["regex", detector])
    assert "live" in str(e.value)
