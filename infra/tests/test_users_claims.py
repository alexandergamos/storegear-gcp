import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import users  # noqa: E402


@pytest.mark.parametrize("role,demo,expected", [
    ("staff", False, {"role": "staff"}),
    ("staff", True, {"role": "staff", "demo": True}),
    ("manager", False, {"role": "manager"}),
    ("none", True, {}),   # no role means no access at all, demo or not
    ("none", False, {}),
])
def test_claims_for(role, demo, expected):
    assert users.claims_for(role, demo) == expected


def test_current_claims_reads_custom_attributes(monkeypatch):
    monkeypatch.setattr(users, "call", lambda s, path, body: {"users": [{"localId": "u1", "customAttributes": '{"role": "staff", "demo": true}'}]})
    assert users.current_claims(None, "a@b.c") == ("u1", "staff", True)
    monkeypatch.setattr(users, "call", lambda s, path, body: {"users": [{"localId": "u1"}]})
    assert users.current_claims(None, "a@b.c") == ("u1", "none", False)
    monkeypatch.setattr(users, "call", lambda s, path, body: {})
    assert users.current_claims(None, "a@b.c") is None
