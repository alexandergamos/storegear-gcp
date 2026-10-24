"""The contract both stores follow, checked on MemoryStore (PgStore runs the same rules in SQL; checked live in Task 11)."""
import pytest

from store import MemoryStore


@pytest.fixture
def s():
    return MemoryStore()


def _cmp(s, cid, uid="u1", a_error=False, b_error=False, q="¿Precio del Venu X1?"):
    return s.add_comparison(cid, uid, q, 9100, 3800, a_error, b_error)


def test_conversation_belongs_to_its_user(s):
    cid = s.create_conversation("u1", "gcp")
    c = s.get_conversation(cid, "u1")
    assert (c.id, c.uid, c.mapping_a, c.gcp_session_id, c.revealed) == (cid, "u1", "gcp", None, False)
    assert s.get_conversation(cid, "u2") is None
    assert s.get_conversation("nope", "u1") is None


def test_gcp_session_is_stored(s):
    cid = s.create_conversation("u1", "n8n")
    s.set_gcp_session(cid, "sess-1")
    assert s.get_conversation(cid, "u1").gcp_session_id == "sess-1"


def test_vote_once(s):
    cid = s.create_conversation("u1", "gcp")
    k = _cmp(s, cid)
    assert s.vote(k, "u2", "A") == "not_found"
    assert s.vote("nope", "u1", "A") == "not_found"
    assert s.vote(k, "u1", "A") == "ok"
    assert s.vote(k, "u1", "B") == "conflict"


@pytest.mark.parametrize("a_error,b_error", [(True, False), (False, True)])
def test_no_vote_when_a_slot_failed(s, a_error, b_error):
    cid = s.create_conversation("u1", "gcp")
    assert s.vote(_cmp(s, cid, a_error=a_error, b_error=b_error), "u1", "tie") == "conflict"


def test_no_vote_after_reveal(s):
    cid = s.create_conversation("u1", "gcp")
    k = _cmp(s, cid)
    s.reveal(cid, "u1")
    assert s.vote(k, "u1", "A") == "conflict"
    assert s.get_conversation(cid, "u1").revealed is True


def test_reveal(s):
    cid = s.create_conversation("u1", "n8n")
    k1 = _cmp(s, cid, q="primera")
    k2 = _cmp(s, cid, q="segunda")
    s.vote(k2, "u1", "B")
    assert s.reveal(cid, "u2") is None
    assert s.reveal(cid, "u1") == {
        "mapping": {"A": "n8n", "B": "gcp"},
        "comparisons": [
            {"comparison_id": k1, "question": "primera", "a_total_ms": 9100, "b_total_ms": 3800, "vote": None},
            {"comparison_id": k2, "question": "segunda", "a_total_ms": 9100, "b_total_ms": 3800, "vote": "B"},
        ],
    }
