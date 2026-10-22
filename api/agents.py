"""The two agents the web demo compares, behind the same failure type (ADR-017).

n8n: the master's official build on n8n Cloud. Its webhook checks an HS256 token signed here with a secret
shared only by sg-api (Secret Manager) and the n8n credential; the token says who asks, always as staff.
"""
import os
import time

import httpx
import jwt

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
