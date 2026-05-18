"""Unit tests for MCP server tools and helpers."""

from __future__ import annotations

import httpx
import pytest
import respx

from app import server as server_module
from app.server import (
    _internal_headers,
    get_user_email,
    get_user_memory,
    mcp,
    search_telegram_chats,
)

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestInternalHeaders:
    def test_returns_token_header_when_set(self, mcp_settings):
        assert _internal_headers() == {"X-Internal-Token": "test-token"}

    def test_returns_empty_dict_when_token_missing(self, mcp_settings_no_token):
        assert _internal_headers() == {}


class TestToolRegistry:
    async def test_get_user_email_registered(self):
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "get_user_email" in names

    async def test_tool_has_description(self):
        tool = await mcp.get_tool("get_user_email")
        assert tool is not None
        assert tool.description
        assert "user" in tool.description.lower()


class TestGetUserEmail:
    async def test_invalid_uuid_returns_error_without_http_call(
        self, mcp_settings, respx_mock
    ):
        result = await get_user_email("not-a-uuid")
        assert result == {"email": "", "error": "Invalid user_id format"}
        assert len(respx_mock.calls) == 0

    async def test_empty_string_returns_error(self, mcp_settings):
        result = await get_user_email("")
        assert result["email"] == ""
        assert "Invalid" in result["error"]

    @respx.mock
    async def test_happy_path_returns_email(self, mcp_settings):
        route = respx.get(
            f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email"
        ).mock(return_value=httpx.Response(200, json={"email": "user@example.com"}))

        result = await get_user_email(VALID_UUID)

        assert result == {"email": "user@example.com"}
        assert route.called
        request = route.calls.last.request
        assert request.headers.get("X-Internal-Token") == "test-token"

    @respx.mock
    async def test_no_token_omits_header(self, mcp_settings_no_token):
        route = respx.get(
            f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email"
        ).mock(return_value=httpx.Response(200, json={"email": "u@example.com"}))

        result = await get_user_email(VALID_UUID)

        assert result == {"email": "u@example.com"}
        assert route.called
        assert "X-Internal-Token" not in route.calls.last.request.headers

    @respx.mock
    async def test_backend_url_trailing_slash_stripped(self, monkeypatch):
        from app.config import Settings

        s = Settings(
            BACKEND_URL="http://backend.test/",
            INTERNAL_API_TOKEN="t",
            REQUEST_TIMEOUT_SECONDS=1.0,
        )
        monkeypatch.setattr(server_module, "settings", s)

        route = respx.get(
            f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email"
        ).mock(return_value=httpx.Response(200, json={"email": "x@y.z"}))

        await get_user_email(VALID_UUID)
        assert route.called

    @respx.mock
    async def test_404_returns_user_not_found(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            return_value=httpx.Response(404)
        )

        result = await get_user_email(VALID_UUID)

        assert result == {"email": "", "error": "User not found"}

    @respx.mock
    async def test_401_returns_unauthorized(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            return_value=httpx.Response(401)
        )

        result = await get_user_email(VALID_UUID)

        assert result == {
            "email": "",
            "error": "Unauthorized (internal token invalid)",
        }

    @respx.mock
    @pytest.mark.parametrize("status", [400, 403, 422, 500, 502, 503])
    async def test_other_error_statuses(self, mcp_settings, status):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            return_value=httpx.Response(status)
        )

        result = await get_user_email(VALID_UUID)

        assert result == {"email": "", "error": f"Backend error: {status}"}

    @respx.mock
    async def test_network_failure_returns_unreachable(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await get_user_email(VALID_UUID)

        assert result["email"] == ""
        assert result["error"].startswith("Backend unreachable:")

    @respx.mock
    async def test_timeout_returns_unreachable(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await get_user_email(VALID_UUID)

        assert result["email"] == ""
        assert "Backend unreachable" in result["error"]

    @respx.mock
    async def test_invalid_json_response(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            return_value=httpx.Response(
                200, content=b"not-json", headers={"content-type": "text/plain"}
            )
        )

        result = await get_user_email(VALID_UUID)

        assert result == {"email": "", "error": "Invalid backend response"}

    @respx.mock
    async def test_response_missing_email_field(self, mcp_settings):
        respx.get(f"http://backend.test/api/v1/internal/users/{VALID_UUID}/email").mock(
            return_value=httpx.Response(200, json={"other": "field"})
        )

        result = await get_user_email(VALID_UUID)

        assert result == {"email": ""}


class TestSearchTelegramChats:
    async def test_registered_on_mcp(self):
        names = {t.name for t in await mcp.list_tools()}
        assert "search_telegram_chats" in names

    async def test_returns_hits_from_rag(self, monkeypatch):
        fake_hits = [
            {
                "doc_id": "thread:1:1",
                "distance": 0.21,
                "chat_id": 1,
                "kind": "thread",
                "n_msgs": 3,
                "date_min": "2026-01-01T00:00:00Z",
                "date_max": "2026-01-01T00:05:00Z",
                "snippet": "visa info",
            }
        ]
        monkeypatch.setattr(server_module.rag, "search", lambda q, k=5: fake_hits)
        result = await search_telegram_chats("how to get visa", k=3)
        assert result == {"hits": fake_hits}

    async def test_empty_query_returns_error_without_calling_rag(self, monkeypatch):
        called = {"n": 0}

        def fake(q, k=5):
            called["n"] += 1
            return []

        monkeypatch.setattr(server_module.rag, "search", fake)
        result = await search_telegram_chats("   ")
        assert result["hits"] == []
        assert "Empty" in result["error"]
        assert called["n"] == 0

    async def test_rag_disabled_returns_error(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setattr(
            server_module,
            "settings",
            Settings(RAG_ENABLED=False, INTERNAL_API_TOKEN="t"),
        )
        result = await search_telegram_chats("x")
        assert result["hits"] == []
        assert "disabled" in result["error"].lower()

    async def test_rag_exception_returns_error(self, monkeypatch):
        def boom(q, k=5):
            raise RuntimeError("ollama down")

        monkeypatch.setattr(server_module.rag, "search", boom)
        result = await search_telegram_chats("anything")
        assert result["hits"] == []
        assert "Retrieval failed" in result["error"]

    async def test_rag_exception_does_not_leak_internal_message(self, monkeypatch):
        def boom(q, k=5):
            raise RuntimeError("postgres://user:secret@db/internal")

        monkeypatch.setattr(server_module.rag, "search", boom)
        result = await search_telegram_chats("x")
        assert "secret" not in result["error"]
        assert "postgres" not in result["error"]
        assert result["error"] == "Retrieval failed"

    async def test_clamps_k_above_max(self, monkeypatch):
        seen = {}

        def capture(q, k=5):
            seen["k"] = k
            return []

        monkeypatch.setattr(server_module.rag, "search", capture)
        await search_telegram_chats("q", k=999)
        assert seen["k"] == server_module.settings.RAG_MAX_K

    async def test_clamps_k_below_one(self, monkeypatch):
        seen = {}

        def capture(q, k=5):
            seen["k"] = k
            return []

        monkeypatch.setattr(server_module.rag, "search", capture)
        await search_telegram_chats("q", k=0)
        assert seen["k"] == 1

    async def test_invalid_k_type_returns_error(self, monkeypatch):
        called = {"n": 0}

        def fake(q, k=5):
            called["n"] += 1
            return []

        monkeypatch.setattr(server_module.rag, "search", fake)
        result = await search_telegram_chats("q", k="abc")  # type: ignore[arg-type]
        assert result["hits"] == []
        assert result["error"] == "Invalid k"
        assert called["n"] == 0

    async def test_offloads_sync_search_to_thread(self, monkeypatch):
        import threading

        main_tid = threading.get_ident()
        captured = {}

        def sync_search(q, k=5):
            captured["tid"] = threading.get_ident()
            return [{"doc_id": "x"}]

        monkeypatch.setattr(server_module.rag, "search", sync_search)
        result = await search_telegram_chats("q", k=3)
        assert result["hits"] == [{"doc_id": "x"}]
        assert captured["tid"] != main_tid


_MEMORIES_URL = f"http://backend.test/api/v1/internal/users/{VALID_UUID}/memories"


class TestGetUserMemory:
    async def test_invalid_uuid_returns_error_without_http_call(
        self, mcp_settings, respx_mock
    ):
        result = await get_user_memory("not-a-uuid")
        assert result == {"memories": [], "error": "Invalid user_id format"}
        assert len(respx_mock.calls) == 0

    @respx.mock
    async def test_list_mode_happy_path(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "memories": [
                        {"id": "m1", "kind": "fact", "content": "User from RU"}
                    ]
                },
            )
        )
        result = await get_user_memory(VALID_UUID)
        assert result == {
            "memories": [{"id": "m1", "kind": "fact", "content": "User from RU"}]
        }
        assert route.called
        req = route.calls.last.request
        assert "query" not in req.url.params
        assert "kind" not in req.url.params
        assert req.url.params["top_k"] == "10"
        assert req.headers.get("X-Internal-Token") == "test-token"

    @respx.mock
    async def test_query_mode_forwards_query(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        await get_user_memory(VALID_UUID, query="where am I from")
        req = route.calls.last.request
        assert req.url.params["query"] == "where am I from"
        assert "kind" not in req.url.params

    @respx.mock
    async def test_query_overrides_kind(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        await get_user_memory(VALID_UUID, query="x", kind="fact")
        req = route.calls.last.request
        assert req.url.params["query"] == "x"
        assert "kind" not in req.url.params

    @respx.mock
    async def test_kind_only(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        await get_user_memory(VALID_UUID, kind="event")
        req = route.calls.last.request
        assert req.url.params["kind"] == "event"
        assert "query" not in req.url.params

    @respx.mock
    async def test_top_k_clamped_low(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        await get_user_memory(VALID_UUID, top_k=0)
        assert route.calls.last.request.url.params["top_k"] == "1"

    @respx.mock
    async def test_top_k_clamped_high(self, mcp_settings):
        route = respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        await get_user_memory(VALID_UUID, top_k=999)
        assert route.calls.last.request.url.params["top_k"] == "50"

    @respx.mock
    async def test_401_returns_unauthorized(self, mcp_settings):
        respx.get(_MEMORIES_URL).mock(return_value=httpx.Response(401))
        result = await get_user_memory(VALID_UUID)
        assert result == {
            "memories": [],
            "error": "Unauthorized (internal token invalid)",
        }

    @respx.mock
    async def test_400_returns_bad_request(self, mcp_settings):
        respx.get(_MEMORIES_URL).mock(return_value=httpx.Response(400))
        result = await get_user_memory(VALID_UUID)
        assert result == {
            "memories": [],
            "error": "Bad request (invalid kind or id)",
        }

    @respx.mock
    @pytest.mark.parametrize("status", [403, 422, 500, 502, 503])
    async def test_other_error_statuses(self, mcp_settings, status):
        respx.get(_MEMORIES_URL).mock(return_value=httpx.Response(status))
        result = await get_user_memory(VALID_UUID)
        assert result == {"memories": [], "error": f"Backend error: {status}"}

    @respx.mock
    async def test_network_failure(self, mcp_settings):
        respx.get(_MEMORIES_URL).mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        result = await get_user_memory(VALID_UUID)
        assert result["memories"] == []
        assert result["error"].startswith("Backend unreachable:")

    @respx.mock
    async def test_invalid_json(self, mcp_settings):
        respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(
                200, content=b"not-json", headers={"content-type": "text/plain"}
            )
        )
        result = await get_user_memory(VALID_UUID)
        assert result == {"memories": [], "error": "Invalid backend response"}

    @respx.mock
    async def test_response_missing_memories_field(self, mcp_settings):
        respx.get(_MEMORIES_URL).mock(
            return_value=httpx.Response(200, json={"other": "field"})
        )
        result = await get_user_memory(VALID_UUID)
        assert result == {"memories": []}

    async def test_tool_registered(self):
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "get_user_memory" in names

    async def test_tool_has_description(self):
        tool = await mcp.get_tool("get_user_memory")
        assert tool is not None
        assert tool.description
        assert (
            "memory" in tool.description.lower() or "facts" in tool.description.lower()
        )
