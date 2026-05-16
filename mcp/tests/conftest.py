"""Shared fixtures for MCP unit tests."""

from __future__ import annotations

import pytest

from app import server as server_module
from app.config import Settings


@pytest.fixture
def mcp_settings(monkeypatch) -> Settings:
    """Provide deterministic settings + patch the module-level singleton."""
    test_settings = Settings(
        MCP_PORT=8001,
        BACKEND_URL="http://backend.test",
        INTERNAL_API_TOKEN="test-token",
        REQUEST_TIMEOUT_SECONDS=1.0,
    )
    monkeypatch.setattr(server_module, "settings", test_settings)
    return test_settings


@pytest.fixture
def mcp_settings_no_token(monkeypatch) -> Settings:
    """Settings without INTERNAL_API_TOKEN."""
    test_settings = Settings(
        MCP_PORT=8001,
        BACKEND_URL="http://backend.test",
        INTERNAL_API_TOKEN=None,
        REQUEST_TIMEOUT_SECONDS=1.0,
    )
    monkeypatch.setattr(server_module, "settings", test_settings)
    return test_settings
