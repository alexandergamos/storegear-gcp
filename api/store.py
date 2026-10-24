"""Blind comparisons for the web demo (ADR-017): which agent is A in each conversation, and the votes.

Both stores follow the same rules: everything is scoped to the uid from the verified token, another user's id
looks exactly like a missing one, a comparison gets at most one vote, never when a slot failed, never after reveal.
"""
import threading
import uuid
from dataclasses import dataclass, replace
from typing import Callable, Literal, Protocol

Agent = Literal["gcp", "n8n"]
Vote = Literal["A", "B", "tie"]
VoteResult = Literal["ok", "not_found", "conflict"]


@dataclass(frozen=True)
class Conversation:
    id: str
    uid: str
    mapping_a: Agent
    gcp_session_id: str | None
    revealed: bool


def other(agent: Agent) -> Agent:
    return "n8n" if agent == "gcp" else "gcp"


def reveal_payload(mapping_a: Agent, rows: list[tuple]) -> dict:
    return {"mapping": {"A": mapping_a, "B": other(mapping_a)},
            "comparisons": [{"comparison_id": r[0], "question": r[1], "a_total_ms": r[2], "b_total_ms": r[3], "vote": r[4]}
                            for r in rows]}


class CompareStore(Protocol):
    def create_conversation(self, uid: str, mapping_a: Agent) -> str: ...
    def get_conversation(self, conversation_id: str, uid: str) -> Conversation | None: ...
    def set_gcp_session(self, conversation_id: str, session_id: str) -> None: ...
    def add_comparison(self, conversation_id: str, uid: str, question: str, a_total_ms: int, b_total_ms: int,
                       a_error: bool, b_error: bool) -> str: ...
    def vote(self, comparison_id: str, uid: str, vote: Vote) -> VoteResult: ...
    def reveal(self, conversation_id: str, uid: str) -> dict | None: ...


class MemoryStore:
    """In-process store for tests."""

    def __init__(self):
        self.conversations: dict[str, Conversation] = {}
        self.comparisons: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_conversation(self, uid, mapping_a):
        cid = uuid.uuid4().hex
        self.conversations[cid] = Conversation(cid, uid, mapping_a, None, False)
        return cid

    def get_conversation(self, conversation_id, uid):
        c = self.conversations.get(conversation_id)
        return c if c and c.uid == uid else None

    def set_gcp_session(self, conversation_id, session_id):
        self.conversations[conversation_id] = replace(self.conversations[conversation_id], gcp_session_id=session_id)

    def add_comparison(self, conversation_id, uid, question, a_total_ms, b_total_ms, a_error, b_error):
        k = uuid.uuid4().hex
        self.comparisons[k] = {"conversation_id": conversation_id, "uid": uid, "question": question, "a_total_ms": a_total_ms,
                               "b_total_ms": b_total_ms, "a_error": a_error, "b_error": b_error, "vote": None}
        return k

    def vote(self, comparison_id, uid, vote):
        with self._lock:
            c = self.comparisons.get(comparison_id)
            if not c or c["uid"] != uid:
                return "not_found"
            if c["vote"] or c["a_error"] or c["b_error"] or self.conversations[c["conversation_id"]].revealed:
                return "conflict"
            c["vote"] = vote
            return "ok"

    def reveal(self, conversation_id, uid):
        c = self.get_conversation(conversation_id, uid)
        if not c:
            return None
        self.conversations[conversation_id] = replace(c, revealed=True)
        rows = [(k, x["question"], x["a_total_ms"], x["b_total_ms"], x["vote"])
                for k, x in self.comparisons.items() if x["conversation_id"] == conversation_id]
        return reveal_payload(c.mapping_a, rows)


class PgStore:
    """Cloud SQL store (tables from infra/sql/009_web_demo.sql). `db` returns a new pg8000 connection."""

    def __init__(self, db: Callable):
        self.db = db

    def _run(self, fn):
        conn = self.db()
        try:
            out = fn(conn.cursor())
            conn.commit()
            return out
        finally:
            conn.close()

    def create_conversation(self, uid, mapping_a):
        cid = uuid.uuid4().hex
        self._run(lambda cur: cur.execute("INSERT INTO compare_conversations (id, uid, mapping_a) VALUES (%s, %s, %s)",
                                          (cid, uid, mapping_a)))
        return cid

    def get_conversation(self, conversation_id, uid):
        def q(cur):
            cur.execute("""SELECT id, uid, mapping_a, gcp_session_id, revealed_at IS NOT NULL
                           FROM compare_conversations WHERE id = %s AND uid = %s""", (conversation_id, uid))
            return cur.fetchone()
        row = self._run(q)
        return Conversation(*row) if row else None

    def set_gcp_session(self, conversation_id, session_id):
        self._run(lambda cur: cur.execute("UPDATE compare_conversations SET gcp_session_id = %s WHERE id = %s",
                                          (session_id, conversation_id)))

    def add_comparison(self, conversation_id, uid, question, a_total_ms, b_total_ms, a_error, b_error):
        k = uuid.uuid4().hex
        self._run(lambda cur: cur.execute(
            """INSERT INTO compare_votes (id, conversation_id, uid, question, a_total_ms, b_total_ms, a_error, b_error)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (k, conversation_id, uid, question, a_total_ms, b_total_ms, a_error, b_error)))
        return k

    def vote(self, comparison_id, uid, vote):
        def q(cur):
            cur.execute("SELECT 1 FROM compare_votes WHERE id = %s AND uid = %s", (comparison_id, uid))
            if not cur.fetchone():
                return "not_found"
            # one statement decides: still unvoted, both slots answered, conversation not revealed
            cur.execute("""UPDATE compare_votes v SET vote = %s, voted_at = now()
                           FROM compare_conversations c
                           WHERE v.id = %s AND v.uid = %s AND v.vote IS NULL AND NOT v.a_error AND NOT v.b_error
                             AND c.id = v.conversation_id AND c.revealed_at IS NULL
                           RETURNING v.id""", (vote, comparison_id, uid))
            return "ok" if cur.fetchone() else "conflict"
        return self._run(q)

    def reveal(self, conversation_id, uid):
        def q(cur):
            cur.execute("""UPDATE compare_conversations SET revealed_at = coalesce(revealed_at, now())
                           WHERE id = %s AND uid = %s RETURNING mapping_a""", (conversation_id, uid))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("""SELECT id, question, a_total_ms, b_total_ms, vote FROM compare_votes
                           WHERE conversation_id = %s ORDER BY created_at, id""", (conversation_id,))
            return reveal_payload(row[0], cur.fetchall())
        return self._run(q)
