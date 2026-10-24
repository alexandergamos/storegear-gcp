import main


def test_compare_requires_token(client):
    r = client.post("/compare", json={"message": "hola"})
    assert r.status_code == 401


def test_compare_requires_demo(client, as_user):
    as_user(demo=False)
    r = client.post("/compare", json={"message": "hola"})
    assert r.status_code == 403
    assert r.json() == {"detail": "demo only"}


def test_user_demo_claim_parsing(monkeypatch):
    monkeypatch.setattr(main.id_token, "verify_firebase_token", lambda *a, **k: {"sub": "u1", "role": "staff", "demo": True})
    assert main.user("Bearer x")["demo"] is True
    monkeypatch.setattr(main.id_token, "verify_firebase_token", lambda *a, **k: {"sub": "u1", "role": "staff", "demo": "true"})
    assert main.user("Bearer x")["demo"] is False
