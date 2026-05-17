"""Unit tests for app/services/ai_agent.py with OpenAI + MCP mocked."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import ai_agent as agent_mod


def _stub_openai_response(content: str | None = None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


class _StubAsyncOpenAI:
    def __init__(self, scripted_responses):
        self._scripted = list(scripted_responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **_kw):
        return self._scripted.pop(0)


@pytest.fixture(autouse=True)
def _clear_history():
    agent_mod._conversation_history.clear()
    yield
    agent_mod._conversation_history.clear()


@pytest.fixture(autouse=True)
def _disable_langfuse(monkeypatch):
    monkeypatch.setattr(agent_mod, "get_langfuse", lambda: None)


def test_get_ai_agent_service_singleton():
    a = agent_mod.get_ai_agent_service()
    b = agent_mod.get_ai_agent_service()
    assert a is b


async def test_chat_returns_plain_response(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()
    service._openai_client = _StubAsyncOpenAI(
        [_stub_openai_response(content="hello world")]
    )
    resp, conv, trace = await service.chat("hi", uuid4(), None)
    assert resp == "hello world"
    assert conv  # generated UUID
    assert trace is None


async def test_chat_runs_tool_call_path(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()

    tool_call = SimpleNamespace(
        id="t1",
        function=SimpleNamespace(name="get_user_email", arguments='{"foo":"bar"}'),
    )
    service._openai_client = _StubAsyncOpenAI(
        [
            _stub_openai_response(content=None, tool_calls=[tool_call]),
            _stub_openai_response(content="you are u@x.com"),
        ]
    )

    async def fake_mcp(self, tool_name, arguments, user_id):
        assert tool_name == "get_user_email"
        assert arguments["user_id"] == str(user_id)
        return {"email": "u@x.com"}

    monkeypatch.setattr(agent_mod.AIAgentService, "_call_mcp_tool", fake_mcp)

    resp, conv, _ = await service.chat("email?", uuid4(), None)
    assert resp == "you are u@x.com"
    assert conv


async def test_chat_preserves_conversation_id(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()
    service._openai_client = _StubAsyncOpenAI([_stub_openai_response(content="ok")])
    _, conv, _ = await service.chat("hi", uuid4(), "fixed-id")
    assert conv == "fixed-id"
    assert agent_mod._conversation_history["fixed-id"]


def test_get_openai_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", None, raising=False)
    service = agent_mod.AIAgentService()
    with pytest.raises(ValueError):
        service._get_openai()
