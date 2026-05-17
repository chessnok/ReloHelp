"""Tests for Settings loader."""

from __future__ import annotations

from app.config import Settings, settings


class TestSettings:
    def test_defaults(self, monkeypatch):
        for key in (
            "MCP_PORT",
            "BACKEND_URL",
            "INTERNAL_API_TOKEN",
            "REQUEST_TIMEOUT_SECONDS",
            "FIRECRAWL_API_KEY",
            "FIRECRAWL_API_URL",
            "FIRECRAWL_TIMEOUT_SECONDS",
            "FIRECRAWL_SEARCH_LIMIT",
        ):
            monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)
        assert s.MCP_PORT == 8001
        assert s.BACKEND_URL == "http://backend:8000"
        assert s.INTERNAL_API_TOKEN is None
        assert s.REQUEST_TIMEOUT_SECONDS == 5.0
        assert s.FIRECRAWL_API_KEY is None
        assert s.FIRECRAWL_API_URL == "https://api.firecrawl.dev"
        assert s.FIRECRAWL_TIMEOUT_SECONDS == 30.0
        assert s.FIRECRAWL_SEARCH_LIMIT == 5

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MCP_PORT", "9999")
        monkeypatch.setenv("BACKEND_URL", "http://api.example.com")
        monkeypatch.setenv("INTERNAL_API_TOKEN", "secret")
        monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "10.5")
        monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-secret")
        monkeypatch.setenv("FIRECRAWL_API_URL", "http://firecrawl.local")
        monkeypatch.setenv("FIRECRAWL_TIMEOUT_SECONDS", "12.5")
        monkeypatch.setenv("FIRECRAWL_SEARCH_LIMIT", "10")
        s = Settings(_env_file=None)
        assert s.MCP_PORT == 9999
        assert s.BACKEND_URL == "http://api.example.com"
        assert s.INTERNAL_API_TOKEN == "secret"
        assert s.REQUEST_TIMEOUT_SECONDS == 10.5
        assert s.FIRECRAWL_API_KEY == "fc-secret"
        assert s.FIRECRAWL_API_URL == "http://firecrawl.local"
        assert s.FIRECRAWL_TIMEOUT_SECONDS == 12.5
        assert s.FIRECRAWL_SEARCH_LIMIT == 10

    def test_singleton_is_settings_instance(self):
        assert isinstance(settings, Settings)

    def test_extra_env_ignored(self, monkeypatch):
        monkeypatch.setenv("SOME_UNRELATED_VAR", "value")
        s = Settings(_env_file=None)
        assert not hasattr(s, "SOME_UNRELATED_VAR")
