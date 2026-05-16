"""Unit tests for app/core/rate_limit.py."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from app.core import rate_limit
from app.core.config import settings


class _StubRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True


def _make_request(host: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (host, 12345),
    }
    return Request(scope)


async def test_disabled_always_allows(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    assert await rate_limit.check_rate_limit(_StubRedis(), "k", 1, 60) is True


async def test_enabled_returns_false_after_max(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    r = _StubRedis()
    assert await rate_limit.check_rate_limit(r, "k", 2, 60) is True
    assert await rate_limit.check_rate_limit(r, "k", 2, 60) is True
    assert await rate_limit.check_rate_limit(r, "k", 2, 60) is False
    assert r.expires["k"] == 60


async def test_get_rate_limit_key_includes_ip():
    key = await rate_limit.get_rate_limit_key(_make_request("9.9.9.9"), "id")
    assert key == "rate_limit:id:9.9.9.9"


async def test_get_rate_limit_key_unknown_when_no_client():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": None,
    }
    req = Request(scope)
    assert "unknown" in await rate_limit.get_rate_limit_key(req, "x")


async def test_check_login_rate_limit_raises_429(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60)
    r = _StubRedis()
    req = _make_request()
    await rate_limit.check_login_rate_limit(r, req, "e@x.com")
    with pytest.raises(HTTPException) as exc:
        await rate_limit.check_login_rate_limit(r, req, "e@x.com")
    assert exc.value.status_code == 429
