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


class TestToolRegistry:
    def test_find_official_info_in_default_tools(self):
        names = {t["function"]["name"] for t in agent_mod.DEFAULT_TOOLS}
        assert "find_official_info" in names
        assert "get_user_email" in names

    def test_find_official_info_tool_schema(self):
        tool = agent_mod.FIND_OFFICIAL_INFO_TOOL
        assert tool["type"] == "function"
        params = tool["function"]["parameters"]
        assert "query" in params["properties"]
        assert "limit" in params["properties"]
        assert params["required"] == ["query"]
        # user_id MUST NOT be in the schema — it's not a user-scoped tool
        assert "user_id" not in params["properties"]

    def test_find_official_info_not_user_scoped(self):
        assert "find_official_info" not in agent_mod._USER_SCOPED_TOOLS
        assert "get_user_email" in agent_mod._USER_SCOPED_TOOLS


class TestSystemInstructions:
    def test_mentions_find_official_info_and_official(self):
        assert "find_official_info" in agent_mod.SYSTEM_INSTRUCTIONS
        assert "official" in agent_mod.SYSTEM_INSTRUCTIONS.lower()

    def test_matches_mcp_server_instructions(self):
        """Both copies of SYSTEM_INSTRUCTIONS must stay in sync.

        The MCP server's FastMCP(instructions=...) is only seen by MCP-aware
        clients; the backend uses its own copy as the OpenAI system prompt.
        Drift would silently change agent behaviour on only one path.
        """
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        mcp_server_text = (repo_root / "mcp" / "app" / "server.py").read_text()

        marker = 'SYSTEM_INSTRUCTIONS = """\\\n'
        start = mcp_server_text.index(marker) + len(marker)
        end = mcp_server_text.index('"""', start)
        mcp_instructions = mcp_server_text[start:end]

        assert agent_mod.SYSTEM_INSTRUCTIONS == mcp_instructions, (
            "Backend SYSTEM_INSTRUCTIONS drifted from mcp/app/server.py. "
            "Update both copies together."
        )


async def test_chat_prepends_system_message(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()

    captured = {}

    async def _create(**kw):
        captured.setdefault("messages", kw["messages"])
        captured.setdefault("tools", kw["tools"])
        return _stub_openai_response(content="ok")

    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    await service.chat("hi", uuid4(), None)

    assert captured["messages"][0]["role"] == "system"
    assert "find_official_info" in captured["messages"][0]["content"]
    tool_names = {t["function"]["name"] for t in captured["tools"]}
    assert tool_names == {"get_user_email", "find_official_info"}


async def test_chat_calls_find_official_info_without_user_id(monkeypatch):
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()

    tool_call = SimpleNamespace(
        id="t1",
        function=SimpleNamespace(
            name="find_official_info",
            arguments='{"query": "Portugal D7 visa 2026"}',
        ),
    )
    service._openai_client = _StubAsyncOpenAI(
        [
            _stub_openai_response(content=None, tool_calls=[tool_call]),
            _stub_openai_response(content="Per imigrante.sef.pt …"),
        ]
    )

    seen = {}

    async def fake_mcp(self, tool_name, arguments, user_id):
        seen["name"] = tool_name
        seen["arguments"] = arguments
        return {"results": [{"url": "https://imigrante.sef.pt/d7", "title": "D7"}]}

    monkeypatch.setattr(agent_mod.AIAgentService, "_call_mcp_tool", fake_mcp)

    resp, _, _ = await service.chat("Portugal D7 income?", uuid4(), None)
    assert resp == "Per imigrante.sef.pt …"
    assert seen["name"] == "find_official_info"
    # find_official_info MUST NOT receive user_id (it doesn't accept it)
    assert "user_id" not in seen["arguments"]
    assert seen["arguments"]["query"] == "Portugal D7 visa 2026"


async def test_call_mcp_tool_injects_user_id_only_for_user_scoped(monkeypatch):
    """_call_mcp_tool injects user_id for get_user_email but strips it for others."""
    service = agent_mod.AIAgentService()
    uid = uuid4()

    captured_params = {}

    class _FakeContent:
        def __init__(self, text):
            self.text = text

    class _FakeResult:
        def __init__(self, payload):
            self.content = [_FakeContent(payload)]

    class _FakeClient:
        def __init__(self, url, timeout):
            self.url = url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def call_tool(self, name, params):
            captured_params[name] = params
            return _FakeResult('{"ok": true}')

    import fastmcp

    monkeypatch.setattr(fastmcp, "Client", _FakeClient)
    monkeypatch.setattr(
        agent_mod.settings, "MCP_SERVER_URL", "http://mcp.test", raising=False
    )

    await service._call_mcp_tool("get_user_email", {}, uid)
    await service._call_mcp_tool(
        "find_official_info", {"query": "q", "user_id": "model-hallucinated"}, uid
    )

    assert captured_params["get_user_email"] == {"user_id": str(uid)}
    assert "user_id" not in captured_params["find_official_info"]
    assert captured_params["find_official_info"]["query"] == "q"


async def test_chat_history_preserves_system_after_trim(monkeypatch):
    """Long conversations should keep the system message at index 0."""
    monkeypatch.setattr(agent_mod.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    service = agent_mod.AIAgentService()
    service._openai_client = _StubAsyncOpenAI(
        [_stub_openai_response(content=f"r{i}") for i in range(25)]
    )

    conv_id = "trim-test"
    # Pre-seed history with 30 fake user/assistant turns (no system message).
    agent_mod._conversation_history[conv_id] = [
        {"role": "user", "content": f"msg{i}"} for i in range(30)
    ]

    await service.chat("ping", uuid4(), conv_id)

    history = agent_mod._conversation_history[conv_id]
    assert history[0]["role"] == "system"
    assert "find_official_info" in history[0]["content"]
    assert len(history) <= 20
