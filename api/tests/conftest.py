"""Shared fixtures for sg-api tests. Nothing here reaches Google or n8n: agents, guards and the database are faked."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STOREGEAR_N8N_JWT_SECRET", "test-secret")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def as_user():
    """as_user(uid, role, demo) makes every request look signed in as that user (no token check)."""
    def _as(uid: str = "u1", role: str = "staff", demo: bool = False) -> dict:
        who = {"uid": uid, "role": role, "demo": demo}
        main.app.dependency_overrides[main.user] = lambda: who
        return who
    yield _as
    main.app.dependency_overrides.pop(main.user, None)


@pytest.fixture
def no_rate_limit(monkeypatch):
    """Replaces the Cloud SQL rate limit with a list that records each uid it was called with."""
    calls: list[str] = []
    monkeypatch.setattr(main, "rate_limit", calls.append)
    return calls
