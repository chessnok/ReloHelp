"""Integration tests for /api/v1/internal/* routes."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings


@pytest.fixture
def internal_token(monkeypatch):
    token = "test-internal-token"
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", token)
    return token


async def test_get_user_email_missing_token_returns_401(client, make_user, internal_token):
    user = await make_user(email="who@example.com")
    resp = await client.get(f"/api/v1/internal/users/{user.id}/email")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing internal token"


async def test_get_user_email_invalid_token_returns_401(
    client, make_user, internal_token
):
    user = await make_user(email="who@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": "wrong"},
    )
    assert resp.status_code == 401


async def test_get_user_email_unset_server_token_rejects_all(
    client, make_user, monkeypatch
):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", None)
    user = await make_user(email="who@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": "anything"},
    )
    assert resp.status_code == 401


async def test_get_user_email_invalid_uuid_returns_400(client, internal_token):
    resp = await client.get(
        "/api/v1/internal/users/not-a-uuid/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid user_id format"


async def test_get_user_email_unknown_user_returns_404(client, internal_token):
    missing = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/internal/users/{missing}/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"


async def test_get_user_email_happy_path(client, make_user, internal_token):
    user = await make_user(email="found@example.com")
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/email",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"email": "found@example.com"}
