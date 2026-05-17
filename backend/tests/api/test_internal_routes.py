"""Tests for internal service-to-service API.

Covers token auth (fail-closed when INTERNAL_API_TOKEN missing/wrong) and
the `/api/v1/internal/users/{user_id}/email` endpoint behavior:
- 401 when token absent
- 401 when token wrong
- 401 fail-closed when server token unset
- 400 on malformed user_id
- 404 on unknown user
- 200 returns email for known user
- empty-string fallback when stored email is None
"""

from __future__ import annotations

import uuid

import pytest_asyncio

from app.core.config import settings

_TEST_TOKEN = "test-internal-token-xyz"


@pytest_asyncio.fixture
async def internal_token(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", _TEST_TOKEN)
    return _TEST_TOKEN


async def test_missing_token_returns_401(client, make_user, internal_token):
    user = await make_user(email="a@example.com")
    resp = await client.get(f"/api/v1/internal/users/{user.id}/email")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing internal token"


async def test_wrong_token_returns_401(client, make_user, internal_token):
    user = await make_user(email="a@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": "wrong"},
    )
    assert resp.status_code == 401


async def test_fail_closed_when_server_token_unset(client, make_user, monkeypatch):
    """Even if caller sends some token, server must reject when its own token is unset."""
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", None)
    user = await make_user(email="a@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": "anything"},
    )
    assert resp.status_code == 401


async def test_fail_closed_when_server_token_empty(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
    user = await make_user(email="a@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": ""},
    )
    assert resp.status_code == 401


async def test_invalid_user_id_format_returns_400(client, internal_token):
    resp = await client.get(
        "/api/v1/internal/users/not-a-uuid/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid user_id format"


async def test_unknown_user_returns_404(client, internal_token):
    missing_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/internal/users/{missing_id}/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"


async def test_returns_user_email(client, make_user, internal_token):
    user = await make_user(email="found@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"email": "found@example.com"}


async def test_returns_empty_string_when_email_none(client, db_session, internal_token):
    """User row with NULL email should produce {"email": ""}."""
    from app.core.security import hash_password
    from app.db.models import User

    user = User(
        id=uuid.uuid4(),
        email=None,
        hashed_password=hash_password("Password123"),
        is_active="active",
        email_is_verified=False,
        roles=[],
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"email": ""}
