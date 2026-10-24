import pytest

import main
from store import MemoryStore


@pytest.fixture
def store(as_user):
    s = MemoryStore()
    main.app.dependency_overrides[main.get_store] = lambda: s
    as_user(demo=True)
    return s


def comparison(store, uid="u1", a_error=False):
    cid = store.create_conversation(uid, "n8n")
    return cid, store.add_comparison(cid, uid, "¿Batería del Grit X2?", 9100, 3800, a_error, False)


def vote(client, k, v="A"):
    return client.post(f"/compare/{k}/vote", json={"vote": v})


def test_vote_ok_without_mapping(client, store):
    _, k = comparison(store)
    r = vote(client, k)
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_second_vote_is_409(client, store):
    _, k = comparison(store)
    vote(client, k)
    assert vote(client, k, "B").status_code == 409


def test_other_users_comparison_is_404(client, store):
    _, k = comparison(store, uid="u2")
    assert vote(client, k).status_code == 404
    assert vote(client, "unknown").status_code == 404


def test_invalid_vote_is_422(client, store):
    _, k = comparison(store)
    assert vote(client, k, "C").status_code == 422


def test_failed_comparison_is_not_votable(client, store):
    _, k = comparison(store, a_error=True)
    assert vote(client, k).status_code == 409


def test_vote_needs_demo(client, store, as_user):
    _, k = comparison(store)
    as_user(demo=False)
    assert vote(client, k).status_code == 403


def test_reveal(client, store):
    cid, k = comparison(store)
    vote(client, k, "tie")
    r = client.post(f"/conversations/{cid}/reveal")
    assert r.status_code == 200
    assert r.json() == {"mapping": {"A": "n8n", "B": "gcp"},
                        "comparisons": [{"comparison_id": k, "question": "¿Batería del Grit X2?",
                                         "a_total_ms": 9100, "b_total_ms": 3800, "vote": "tie"}]}


def test_reveal_other_user_is_404(client, store):
    cid, _ = comparison(store, uid="u2")
    assert client.post(f"/conversations/{cid}/reveal").status_code == 404


def test_after_reveal_no_votes_no_questions(client, store, no_rate_limit):
    cid, k = comparison(store)
    client.post(f"/conversations/{cid}/reveal")
    assert vote(client, k).status_code == 409
    r = client.post("/compare", json={"message": "otra", "conversation_id": cid})
    assert r.status_code == 409
