"""The two agents the web demo compares, behind the same failure type (ADR-017).

n8n: the master's official build on n8n Cloud. Its webhook checks an HS256 token signed here with a secret
shared only by sg-api (Secret Manager) and the n8n credential; the token says who asks, always as staff.

Google Cloud: the Agent Runtime agent behind sg-api's guardrails (ADR-015), as a stream of progress steps.
"""
import os
import time
from typing import Callable, Iterator

import httpx
import jwt

import guards

N8N_URL = os.getenv("STOREGEAR_N8N_URL", "https://thebridge.app.n8n.cloud/webhook/storegear-agent")
N8N_TIMEOUT = 120   # seconds; the n8n agent's slowest answers in the eval were ~40 s
TOKEN_TTL = 60


class AgentError(Exception):
    """An agent didn't give a usable answer. The message is for logs, never for the client."""


def n8n_token(uid: str, now: float) -> str:
    secret = os.getenv("STOREGEAR_N8N_JWT_SECRET")
    if not secret:
        raise AgentError("n8n secret not configured")
    return jwt.encode({"sub": uid, "role": "staff", "exp": int(now) + TOKEN_TTL}, secret, algorithm="HS256")


def ask_n8n(message: str, uid: str, conversation_id: str, client: httpx.Client | None = None) -> str:
    headers = {"Authorization": f"Bearer {n8n_token(uid, time.time())}"}
    body = {"message": message, "conversationId": conversation_id}
    try:
        if client is None:
            with httpx.Client(timeout=N8N_TIMEOUT) as c:
                r = c.post(N8N_URL, json=body, headers=headers)
        else:
            r = client.post(N8N_URL, json=body, headers=headers)
        data = r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError) as e:
        raise AgentError(f"n8n call failed: {type(e).__name__}") from None
    if r.status_code != 200:
        raise AgentError(f"n8n status {r.status_code}")
    if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("output"), str):
        raise AgentError("n8n answer unusable")
    return data["output"]


# ---------------------------------------------------------------- Google Cloud agent
SESSION_TTL = os.getenv("STOREGEAR_SESSION_TTL", f"{30 * 24 * 3600}s")   # 30 days, then the platform deletes it (ADR-016)
# partial text events tell when drafting starts; off until checked live against Agent Runtime
PARTIAL_EVENTS = os.getenv("STOREGEAR_PARTIAL_EVENTS") == "1"
REPLY = {   # what the employee sees when a guardrail stops a request (ADR-015)
    "blocked": "Lo siento, no puedo ayudar con esa petición. Puedo responder sobre los relojes del catálogo, su precio y stock, y las políticas de la tienda.",
    "off_topic": "Solo puedo ayudarte con los relojes del catálogo (especificaciones, uso, precio y stock) y con las políticas de la tienda. ¿Qué necesitas saber?",
    "leak": "No puedo compartir detalles internos sobre cómo funciono. ¿En qué te ayudo con el catálogo?",
}
CHECK, SEARCH, PRICE, DRAFT = "Pregunta revisada", "Buscando en los manuales", "Consultando precio y stock", "Redactando la respuesta"
ORDER = [CHECK, SEARCH, PRICE, DRAFT]
TOOL_STEP = {"buscar_catalogo_hibrido": SEARCH, "consultar_precio_stock": PRICE}


class _Steps:
    """Fixed labels, forward only: each label runs once, a later event can't send the list back (spec §6.2)."""

    def __init__(self, clock):
        self.clock, self.current, self.t = clock, None, 0.0

    def start(self, label: str) -> Iterator[dict]:
        if self.current and ORDER.index(label) <= ORDER.index(self.current):
            return
        yield from self.finish()
        self.current, self.t = label, self.clock()
        yield {"type": "step", "label": label, "status": "running"}

    def finish(self) -> Iterator[dict]:
        if self.current:
            yield {"type": "step", "label": self.current, "status": "done", "ms": max(0, round((self.clock() - self.t) * 1000))}
        self.current = None


def _error(status: int, message: str, reason: str | None = None) -> dict:
    """`message` may reach the client (/chat); `reason` is for our log only."""
    e = {"type": "error", "status": status, "message": message}
    if reason:
        e["reason"] = reason
    return e


def _why(guard: str, ex: Exception) -> str:
    """Which guard failed and how, for the log: the error kind and its HTTP code, never its text (it may echo input)."""
    code = getattr(getattr(ex, "response", None), "status_code", None) or getattr(ex, "code", None)
    return f"{guard}: {type(ex).__name__}" + (f" {code}" if isinstance(code, int) else "")


def add_usage(total: dict | None, um: dict | None) -> dict | None:
    """Adds one model call's usage_metadata to the answer's running total (SMO-26). Thinking is billed as output."""
    if not um:
        return total
    t = total or {"tokens_in": 0, "tokens_cached": 0, "tokens_out": 0, "model_calls": 0}
    return {"tokens_in": t["tokens_in"] + (um.get("prompt_token_count") or 0),
            "tokens_cached": t["tokens_cached"] + (um.get("cached_content_token_count") or 0),
            "tokens_out": t["tokens_out"] + (um.get("candidates_token_count") or 0) + (um.get("thoughts_token_count") or 0),
            "model_calls": t["model_calls"] + 1}


def gcp_events(get_remote: Callable, uid: str, role: str, message: str, session_id: str | None,
               clock=time.monotonic) -> Iterator[dict]:
    """Steps, then exactly one terminal: answer {text, session_id, guard[, seconds], usage, topic_check} or error {status, message}.

    `message` is already PII-masked by the caller. A guardrail block is a normal answer (the guard's reply).
    `get_remote` is only called once the input guards pass: a blocked question never needs Agent Runtime.
    """
    steps = _Steps(clock)
    yield from steps.start(CHECK)
    # Model Armor FIRST, the topic check (a Gemini call) only if the text is clean: content Model Armor blocks must
    # never reach the model, not even for classification.
    try:
        hits = guards.armor(message)
    except Exception as ex:  # noqa: BLE001  fail closed: an unchecked question never reaches the agent
        yield _error(503, "guardrail unavailable", _why("armor_in", ex))
        return
    if hits:
        yield from steps.finish()
        yield {"type": "answer", "text": REPLY["blocked"], "session_id": session_id, "guard": {"blocked": "input", "filters": hits},
               "usage": None, "topic_check": False}
        return
    # The topic check is a scope filter, not a safety control (ADR-015 addendum, 2026-10-26): when Gemini is too slow
    # to answer it, the question goes on (the agent's prompt keeps it to the catalogue) and the answer records why.
    # Model Armor above and the output guards below still fail closed.
    topic_checked, skipped = True, {}
    try:
        topic_ok = guards.on_topic(message)
    except Exception as ex:  # noqa: BLE001
        topic_ok, topic_checked, skipped = True, False, {"topic_skipped": _why("topic_check", ex)}
    if not topic_ok:
        yield from steps.finish()
        yield {"type": "answer", "text": REPLY["off_topic"], "session_id": session_id, "guard": {"blocked": "off_topic"},
               "usage": None, "topic_check": True}
        return
    remote = get_remote()
    sid = session_id
    if sid:
        try:
            s = remote.get_session(user_id=uid, session_id=sid)   # only the owner's sessions are found
        except Exception:  # noqa: BLE001
            yield _error(404, "session not found")
            return
        if (s.get("state") or {}).get("user:role") != role:
            sid = None   # the role changed since this session started: never reuse it
    if not sid:
        sid = remote.create_session(user_id=uid, state={"user:role": role}, ttl=SESSION_TTL)["id"]

    # the agent searches the manuals before its first model call (pre_retrieval), so "searching" starts here
    yield from steps.start(SEARCH)
    t0, answer, error, usage = time.time(), [], None, None
    kw = {"run_config": {"streaming_mode": "sse"}} if PARTIAL_EVENTS else {}
    for ev in remote.stream_query(user_id=uid, session_id=sid, message=message, **kw):
        if ev.get("error_code"):
            error = ev["error_code"]
        usage = add_usage(usage, ev.get("usage_metadata"))
        for p in (ev.get("content") or {}).get("parts", []) or []:
            call, resp = p.get("function_call"), p.get("function_response")
            if call and call.get("name") in TOOL_STEP:
                yield from steps.start(TOOL_STEP[call["name"]])
            if resp and resp.get("name") == "consultar_precio_stock":
                yield from steps.start(DRAFT)
            if p.get("text") and not p.get("thought") and ev.get("author") != "user":
                yield from steps.start(DRAFT)
                if not ev.get("partial"):
                    answer.append(p["text"])
    if not answer:
        yield _error(502, f"agent error: {error or 'empty answer'}")
        return
    # OUTPUT: leaks of how we're built, links outside the brands, PII, and Model Armor's harm filters
    text = answer[-1]
    found_leak = guards.leak(text)
    if found_leak:
        yield from steps.finish()
        yield {"type": "answer", "text": REPLY["leak"], "session_id": sid, "seconds": round(time.time() - t0, 1),
               "guard": {"blocked": "leak", "leak": found_leak}, "usage": usage, "topic_check": topic_checked, **skipped}
        return
    text, links = guards.strip_links(text)
    text, pii_out = guards.mask_pii(text)
    try:
        hits_out = guards.armor(text, response=True)
    except Exception as ex:  # noqa: BLE001
        yield _error(503, "guardrail unavailable", _why("armor_out", ex))
        return
    yield from steps.finish()
    if hits_out:
        yield {"type": "answer", "text": REPLY["blocked"], "session_id": sid, "seconds": round(time.time() - t0, 1),
               "guard": {"blocked": "output", "filters": hits_out}, "usage": usage, "topic_check": topic_checked, **skipped}
        return
    yield {"type": "answer", "text": text, "session_id": sid, "seconds": round(time.time() - t0, 1),
           "guard": {"pii_out": pii_out, "links_removed": links}, "usage": usage, "topic_check": topic_checked, **skipped}
