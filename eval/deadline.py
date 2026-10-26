"""A deadline for calls that have none (SMO-28 eval gate): Agent Runtime's stream_query and the judge.

The call runs in a daemon thread; after `seconds` the caller moves on. A daemon thread never keeps the process
alive, so one hung call cannot hang the whole run. The gate treats a timed-out answer like any other
availability failure: the question is run once more, never scored as wrong.
"""
import threading
from typing import Callable, TypeVar

T = TypeVar("T")
TIMEOUT_ANSWER = "ERROR timeout: the deployed agent gave no answer in time"


def within(fn: Callable[[], T], seconds: float) -> T:
    box: dict = {}

    def work() -> None:
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001  re-raised in the caller's thread
            box["error"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"no answer in {seconds} s")
    if "error" in box:
        raise box["error"]
    return box["value"]
