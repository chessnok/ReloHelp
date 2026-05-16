"""Integration test for /ping route via httpx ASGI client.

`/ping` runs `SELECT version()` which sqlite cannot do. We override
`get_db_session` with a stub that returns a synthetic version string.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.db.session import get_db_session


class _StubResult:
    def scalar(self):
        return "PostgreSQL 18.0, compiled by ..."


class _StubSession:
    async def execute(self, *_a, **_kw):
        return _StubResult()

    async def close(self):
        return None


async def test_ping_returns_pongi(app_instance, client):
    async def _override():
        yield _StubSession()

    app_instance.dependency_overrides[get_db_session] = _override
    resp = await client.get("/ping")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["message"] == "pongi"
    assert payload["database"] == "connected"
    assert payload["postgres_version"].startswith("PostgreSQL 18.0")
