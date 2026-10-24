import json

import httpx
import jwt
import pytest

import agents


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_token_claims():
    tok = agents.n8n_token("u1", now=1000.0)
    claims = jwt.decode(tok, "test-secret", algorithms=["HS256"], options={"verify_exp": False})
    assert claims == {"sub": "u1", "role": "staff", "exp": 1060}
    assert jwt.get_unverified_header(tok)["alg"] == "HS256"


def test_request_body_and_auth():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"output": "x"})

    assert agents.ask_n8n("¿Precio?", "u1", "c1", client=_client(handler)) == "x"
    assert seen["body"] == {"message": "¿Precio?", "conversationId": "c1"}
    assert seen["url"] == "https://thebridge.app.n8n.cloud/webhook/storegear-agent"
    scheme, tok = seen["auth"].split(" ")
    assert scheme == "Bearer"
    assert jwt.decode(tok, "test-secret", algorithms=["HS256"])["sub"] == "u1"


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"output": "…", "error": "invalid_request"}),
    httpx.Response(500, json={"output": "x"}),
    httpx.Response(200, json={"answer": "x"}),
    httpx.Response(200, text="not json"),
])
def test_failures_raise_agent_error(response):
    with pytest.raises(agents.AgentError):
        agents.ask_n8n("hola", "u1", "c1", client=_client(lambda req: response))


def test_timeout_raises_agent_error():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(agents.AgentError):
        agents.ask_n8n("hola", "u1", "c1", client=_client(handler))
