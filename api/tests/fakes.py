"""Fakes shared by the tests: an Agent Runtime that replays recorded events."""
import json


def ev(*parts, author="storegear", **extra):
    return {"author": author, "content": {"parts": list(parts)}, **extra}


PRICE_EVENTS = [   # Agent Runtime events for "¿Cuánto cuesta el Venu X1 y hay stock?"
    ev({"function_call": {"name": "buscar_catalogo_hibrido", "args": {"query": "Venu X1"}}}),
    ev({"function_response": {"name": "buscar_catalogo_hibrido", "response": {"result": "..."}}}, author="storegear"),
    ev({"function_call": {"name": "consultar_precio_stock", "args": {"file_id": "x" * 30}}}),
    ev({"function_response": {"name": "consultar_precio_stock", "response": {"precio": 549}}}),
    ev({"text": "pensando", "thought": True}, {"text": "El Venu X1 cuesta 549 € y hay 3 en stock."}),
]


class FakeRemote:
    def __init__(self, events, sessions=None):
        self.events, self.sessions, self.calls = events, sessions or {}, []

    def get_session(self, user_id, session_id):
        if (user_id, session_id) not in self.sessions:
            raise RuntimeError("not found")
        return self.sessions[(user_id, session_id)]

    def create_session(self, user_id, state, ttl):
        self.calls.append(("create_session", user_id, state))
        self.sessions[(user_id, "new-session")] = {"state": state}
        return {"id": "new-session"}

    def stream_query(self, user_id, session_id, message, **kw):
        self.calls.append(("stream_query", user_id, session_id, message, kw))
        yield from self.events


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """[(event, data), ...] from a text/event-stream body."""
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out
