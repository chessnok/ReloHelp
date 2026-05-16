"""Integration tests for /api/ai/chat route."""

from __future__ import annotations

import pytest

from app.services import ai_agent as agent_mod


class _FakeAgent:
    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior

    async def chat(self, message, user_id, conversation_id):
        if self.behavior == "ok":
            return "hello", conversation_id or "cid", "tid"
        if self.behavior == "no_key":
            raise ValueError("OPENAI_API_KEY is not set")
        if self.behavior == "bad_value":
            raise ValueError("Bad input")
        raise RuntimeError("boom")


@pytest.fixture
def _agent(monkeypatch):
    fake = _FakeAgent()
    from app.api.v1.routes import ai as ai_route

    monkeypatch.setattr(ai_route, "get_ai_agent_service", lambda: fake)
    return fake


async def test_chat_requires_auth(client):
    resp = await client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 401


async def test_chat_happy_path(client, make_user, access_token_for, _agent):
    u = await make_user()
    client.cookies.set("access_token", access_token_for(u))
    resp = await client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "hello"
    assert body["trace_id"] == "tid"


async def test_chat_no_openai_key_returns_503(
    client, make_user, access_token_for, monkeypatch
):
    fake = _FakeAgent(behavior="no_key")
    from app.api.v1.routes import ai as ai_route

    monkeypatch.setattr(ai_route, "get_ai_agent_service", lambda: fake)
    u = await make_user()
    client.cookies.set("access_token", access_token_for(u))
    resp = await client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 503


async def test_chat_value_error_returns_400(
    client, make_user, access_token_for, monkeypatch
):
    fake = _FakeAgent(behavior="bad_value")
    from app.api.v1.routes import ai as ai_route

    monkeypatch.setattr(ai_route, "get_ai_agent_service", lambda: fake)
    u = await make_user()
    client.cookies.set("access_token", access_token_for(u))
    resp = await client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 400


async def test_chat_generic_error_returns_502(
    client, make_user, access_token_for, monkeypatch
):
    fake = _FakeAgent(behavior="boom")
    from app.api.v1.routes import ai as ai_route

    monkeypatch.setattr(ai_route, "get_ai_agent_service", lambda: fake)
    u = await make_user()
    client.cookies.set("access_token", access_token_for(u))
    resp = await client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 502
