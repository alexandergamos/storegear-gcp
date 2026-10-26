"""A call with no deadline of its own cannot hang the eval gate: it gets one, and a late answer counts as unavailable."""
import threading
import time

import pytest

import deadline
import gate


def test_a_fast_call_returns_its_value():
    assert deadline.within(lambda: 42, seconds=1) == 42


def test_a_hung_call_times_out_on_time():
    never = threading.Event()
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        deadline.within(never.wait, seconds=0.2)
    assert time.monotonic() - t0 < 1


def test_a_failing_call_raises_its_own_error():
    def boom():
        raise ValueError("boom")
    with pytest.raises(ValueError):
        deadline.within(boom, seconds=1)


def test_a_timed_out_answer_is_retried_by_the_gate_not_scored():
    assert gate.is_unavailable({"answer": deadline.TIMEOUT_ANSWER})
