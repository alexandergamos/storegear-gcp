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


def test_jury_command_creates_a_demo_staff_account_and_keeps_the_password_local(monkeypatch):
    calls, written = [], {}
    monkeypatch.setattr(users, "session", lambda: "s")
    monkeypatch.setattr(users, "add", lambda s, email, role, password=None, demo=False: calls.append((email, role, demo)) or ("uid1", "pw-123"))
    monkeypatch.setattr(users, "write_env", written.update)
    users.main(["jury", "jurado@storegear-gcp.test"])
    assert calls == [("jurado@storegear-gcp.test", "staff", True)]
    assert written == {"STOREGEAR_JURY_EMAIL": "jurado@storegear-gcp.test", "STOREGEAR_JURY_PASSWORD": "pw-123"}


def test_a_named_jury_account_gets_its_own_keys_and_leaves_the_first_one_alone(monkeypatch):
    calls, written = [], {}
    monkeypatch.setattr(users, "session", lambda: "s")
    monkeypatch.setattr(users, "add", lambda s, email, role, password=None, demo=False: calls.append((email, role, demo)) or ("uid2", "pw-456"))
    monkeypatch.setattr(users, "write_env", written.update)
    users.main(["jury", "iraitz@storegear-gcp.test", "iraitz"])
    assert calls == [("iraitz@storegear-gcp.test", "staff", True)]
    assert written == {"STOREGEAR_JURY_IRAITZ_EMAIL": "iraitz@storegear-gcp.test", "STOREGEAR_JURY_IRAITZ_PASSWORD": "pw-456"}
