"""Tests for the find_official_info Firecrawl-backed MCP tool."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.server import SYSTEM_INSTRUCTIONS, find_official_info, mcp

FIRECRAWL_SEARCH_URL = "http://firecrawl.test/v1/search"


class TestSystemInstructions:
    def test_mentions_official_and_new(self):
        text = SYSTEM_INSTRUCTIONS.lower()
        assert "official" in text
        assert "new" in text

    def test_mentions_find_official_info(self):
        assert "find_official_info" in SYSTEM_INSTRUCTIONS

    def test_mcp_instructions_set(self):
        assert mcp.instructions == SYSTEM_INSTRUCTIONS


class TestToolRegistry:
    async def test_find_official_info_registered(self):
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "find_official_info" in names

    async def test_tool_has_description(self):
        tool = await mcp.get_tool("find_official_info")
        assert tool is not None
        assert tool.description
        assert "firecrawl" in tool.description.lower()


class TestFindOfficialInfoValidation:
    async def test_empty_query_returns_error(self, mcp_settings):
        result = await find_official_info("")
        assert result == {"results": [], "error": "Query is empty"}

    async def test_whitespace_query_returns_error(self, mcp_settings):
        result = await find_official_info("   ")
        assert result["results"] == []
        assert result["error"] == "Query is empty"

    async def test_missing_api_key_returns_error(self, mcp_settings_no_firecrawl):
        result = await find_official_info("Portugal D7 visa 2026")
        assert result["results"] == []
        assert "FIRECRAWL_API_KEY" in result["error"]


class TestFindOfficialInfoHappyPath:
    @respx.mock
    async def test_returns_normalized_results(self, mcp_settings):
        firecrawl_payload = {
            "success": True,
            "data": [
                {
                    "url": "https://imigrante.sef.pt/d7",
                    "title": "D7 Visa - SEF",
                    "description": "Official D7 visa requirements",
                    "markdown": "# D7\nMinimum income: ...",
                },
                {
                    "url": "https://www.portaldascomunidades.mne.gov.pt/visa",
                    "title": "Ministry of Foreign Affairs - D7",
                    "description": "Embassy procedure",
                    "markdown": "## Procedure",
                },
            ],
        }
        route = respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=firecrawl_payload)
        )

        result = await find_official_info("Portugal D7 visa 2026 official")

        assert "error" not in result
        assert len(result["results"]) == 2
        assert result["results"][0]["url"] == "https://imigrante.sef.pt/d7"
        assert result["results"][0]["title"] == "D7 Visa - SEF"
        assert "Minimum income" in result["results"][0]["markdown"]
        assert route.called

    @respx.mock
    async def test_sends_bearer_token_and_payload(self, mcp_settings):
        route = respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("Germany Blue Card 2026", limit=2)

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer fc-test-key"
        assert request.headers["Content-Type"] == "application/json"

        body = json.loads(request.content)
        assert body["query"] == "Germany Blue Card 2026"
        assert body["limit"] == 2
        assert body["scrapeOptions"]["formats"] == ["markdown"]

    @respx.mock
    async def test_default_limit_from_settings(self, mcp_settings):
        route = respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("test query")

        body = json.loads(route.calls.last.request.content)
        assert body["limit"] == 3

    @respx.mock
    async def test_negative_limit_falls_back_to_default(self, mcp_settings):
        route = respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("test query", limit=-5)

        body = json.loads(route.calls.last.request.content)
        assert body["limit"] == 3

    @respx.mock
    async def test_trailing_slash_stripped_from_api_url(self, monkeypatch):
        from app import server as server_module
        from app.config import Settings

        s = Settings(
            FIRECRAWL_API_KEY="k",
            FIRECRAWL_API_URL="http://firecrawl.test/",
            FIRECRAWL_TIMEOUT_SECONDS=1.0,
            FIRECRAWL_SEARCH_LIMIT=5,
        )
        monkeypatch.setattr(server_module, "settings", s)

        route = respx.post("http://firecrawl.test/v1/search").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("q")
        assert route.called

    @respx.mock
    async def test_results_alt_key_supported(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200, json={"results": [{"url": "https://gov.example", "title": "X"}]}
            )
        )

        result = await find_official_info("q")

        assert result["results"][0]["url"] == "https://gov.example"

    @respx.mock
    async def test_missing_fields_default_to_empty_strings(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": [{}]})
        )

        result = await find_official_info("q")

        assert result["results"][0] == {
            "url": "",
            "title": "",
            "description": "",
            "markdown": "",
            "publishedDate": "",
            "updatedDate": "",
        }

    @respx.mock
    async def test_non_dict_items_filtered(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"url": "https://a"}, "string-item", None, 42]},
            )
        )

        result = await find_official_info("q")
        assert len(result["results"]) == 1
        assert result["results"][0]["url"] == "https://a"


class TestFindOfficialInfoErrors:
    @respx.mock
    async def test_401_returns_unauthorized(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(return_value=httpx.Response(401))

        result = await find_official_info("q")

        assert result == {
            "results": [],
            "error": "Firecrawl unauthorized (bad API key)",
        }

    @respx.mock
    async def test_402_returns_quota(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(return_value=httpx.Response(402))

        result = await find_official_info("q")
        assert result == {"results": [], "error": "Firecrawl quota exhausted"}

    @respx.mock
    async def test_429_returns_rate_limited(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(return_value=httpx.Response(429))

        result = await find_official_info("q")
        assert result == {"results": [], "error": "Firecrawl rate-limited"}

    @respx.mock
    @pytest.mark.parametrize("status", [400, 403, 500, 502, 503])
    async def test_other_errors(self, mcp_settings, status):
        respx.post(FIRECRAWL_SEARCH_URL).mock(return_value=httpx.Response(status))

        result = await find_official_info("q")
        assert result == {"results": [], "error": f"Firecrawl error: {status}"}

    @respx.mock
    async def test_network_failure(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(side_effect=httpx.ConnectError("refused"))

        result = await find_official_info("q")
        assert result["results"] == []
        assert result["error"].startswith("Firecrawl unreachable:")

    @respx.mock
    async def test_timeout(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await find_official_info("q")
        assert "Firecrawl unreachable" in result["error"]

    @respx.mock
    async def test_invalid_json(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200, content=b"not-json", headers={"content-type": "text/plain"}
            )
        )

        result = await find_official_info("q")
        assert result == {"results": [], "error": "Invalid Firecrawl response"}

    @respx.mock
    async def test_empty_data_returns_empty_results(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        result = await find_official_info("q")
        assert result == {"results": []}

    @respx.mock
    async def test_success_false_on_200_returns_error(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={"success": False, "error": "internal blew up", "data": []},
            )
        )

        result = await find_official_info("q")
        assert result["results"] == []
        assert "internal blew up" in result["error"]

    @respx.mock
    async def test_success_false_without_error_field(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"success": False})
        )

        result = await find_official_info("q")
        assert result["results"] == []
        assert "Firecrawl returned failure" in result["error"]


class TestFindOfficialInfoV2Shape:
    @respx.mock
    async def test_nested_data_web_array(self, mcp_settings):
        """v2 shape: data is an object with a 'web' array."""
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "web": [
                            {"url": "https://gov.example/a", "title": "A"},
                            {"url": "https://gov.example/b", "title": "B"},
                        ]
                    },
                },
            )
        )

        result = await find_official_info("q")
        assert len(result["results"]) == 2
        assert result["results"][0]["url"] == "https://gov.example/a"

    @respx.mock
    async def test_body_without_data_or_results(self, mcp_settings):
        """Defensive: payload missing both 'data' and 'results' → empty list."""
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"success": True})
        )

        result = await find_official_info("q")
        assert result == {"results": []}

    @respx.mock
    async def test_nested_data_multiple_buckets(self, mcp_settings):
        """v2 shape: data may contain web + news arrays — merge all."""
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "web": [{"url": "https://w"}],
                        "news": [{"url": "https://n"}],
                    },
                },
            )
        )

        result = await find_official_info("q")
        urls = {r["url"] for r in result["results"]}
        assert urls == {"https://w", "https://n"}


class TestFindOfficialInfoDates:
    @respx.mock
    async def test_published_and_updated_top_level(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "url": "https://gov.example",
                            "publishedDate": "2026-01-15",
                            "updatedDate": "2026-03-01",
                        }
                    ]
                },
            )
        )

        result = await find_official_info("q")
        assert result["results"][0]["publishedDate"] == "2026-01-15"
        assert result["results"][0]["updatedDate"] == "2026-03-01"

    @respx.mock
    async def test_dates_from_metadata(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "url": "https://gov.example",
                            "metadata": {
                                "article:published_time": "2026-02-01T00:00:00Z",
                                "article:modified_time": "2026-02-10T00:00:00Z",
                            },
                        }
                    ]
                },
            )
        )

        result = await find_official_info("q")
        assert result["results"][0]["publishedDate"] == "2026-02-01T00:00:00Z"
        assert result["results"][0]["updatedDate"] == "2026-02-10T00:00:00Z"

    @respx.mock
    async def test_metadata_title_fallback(self, mcp_settings):
        respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "url": "https://gov.example",
                            "metadata": {
                                "title": "Meta Title",
                                "description": "Meta Desc",
                            },
                        }
                    ]
                },
            )
        )

        result = await find_official_info("q")
        assert result["results"][0]["title"] == "Meta Title"
        assert result["results"][0]["description"] == "Meta Desc"


class TestFindOfficialInfoLimitCap:
    @respx.mock
    async def test_user_limit_capped_by_settings(self, mcp_settings):
        """User-provided limit cannot exceed FIRECRAWL_SEARCH_LIMIT (3 in fixture)."""
        route = respx.post(FIRECRAWL_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("q", limit=50)

        body = json.loads(route.calls.last.request.content)
        assert body["limit"] == 3

    @respx.mock
    async def test_hard_cap_at_100(self, monkeypatch):
        """If settings allow more than 100, hard cap kicks in."""
        from app import server as server_module
        from app.config import Settings

        s = Settings(
            FIRECRAWL_API_KEY="k",
            FIRECRAWL_API_URL="http://firecrawl.test",
            FIRECRAWL_TIMEOUT_SECONDS=1.0,
            FIRECRAWL_SEARCH_LIMIT=100,
        )
        monkeypatch.setattr(server_module, "settings", s)

        route = respx.post("http://firecrawl.test/v1/search").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await find_official_info("q", limit=500)

        body = json.loads(route.calls.last.request.content)
        assert body["limit"] == 100
