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


async def _seed_memory(
    db_session,
    user_id,
    kind: str,
    content: str,
    embedding=None,
    metadata=None,
):
    from app.db.models import Memory

    mem = Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        conversation_id=None,
        kind=kind,
        content=content,
        embedding=embedding or [0.0] * 4,
        meta=metadata or {},
    )
    db_session.add(mem)
    await db_session.commit()
    return mem


async def test_get_user_memories_requires_token(client, make_user):
    user = await make_user()
    resp = await client.get(f"/api/v1/internal/users/{user.id}/memories")
    assert resp.status_code == 401


async def test_get_user_memories_invalid_uuid_returns_400(client, internal_token):
    resp = await client.get(
        "/api/v1/internal/users/not-a-uuid/memories",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 400


async def test_get_user_memories_invalid_kind_returns_400(
    client, make_user, internal_token
):
    user = await make_user()
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/memories",
        params={"kind": "garbage"},
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 400


async def test_get_user_memories_lists_all_for_user(
    client, make_user, db_session, internal_token
):
    u1 = await make_user(email="u1@example.com")
    u2 = await make_user(email="u2@example.com")
    await _seed_memory(db_session, u1.id, "fact", "User is from Russia")
    await _seed_memory(db_session, u1.id, "event", "Booked flight")
    await _seed_memory(db_session, u2.id, "fact", "Other user fact")

    resp = await client.get(
        f"/api/v1/internal/users/{u1.id}/memories",
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    contents = {m["content"] for m in resp.json()["memories"]}
    assert contents == {"User is from Russia", "Booked flight"}


async def test_get_user_memories_filters_by_kind(
    client, make_user, db_session, internal_token
):
    user = await make_user()
    await _seed_memory(db_session, user.id, "fact", "User is from Russia")
    await _seed_memory(db_session, user.id, "event", "Booked flight")

    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/memories",
        params={"kind": "event"},
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    rows = resp.json()["memories"]
    assert len(rows) == 1
    assert rows[0]["content"] == "Booked flight"
    assert rows[0]["kind"] == "event"


async def test_get_user_memories_respects_top_k(
    client, make_user, db_session, internal_token
):
    user = await make_user()
    for i in range(5):
        await _seed_memory(db_session, user.id, "fact", f"fact-{i}")

    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/memories",
        params={"top_k": 2},
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    assert len(resp.json()["memories"]) == 2


async def test_get_user_memories_semantic_query_calls_search(
    client, make_user, internal_token, monkeypatch
):
    """When `query` is set, the route delegates to MemoryService.search."""
    user = await make_user()
    from app.api.v1.routes import internal as internal_route
    from app.services.memory import MemoryHit

    hit = MemoryHit(
        id=uuid.uuid4(),
        kind="fact",
        content="User is from Russia",
        similarity=0.83,
        metadata={"src": "extract"},
    )

    class _StubSvc:
        async def search(self, db, uid, q, top_k=None, threshold=None):
            return [hit]

    monkeypatch.setattr(internal_route, "get_memory_service", lambda: _StubSvc())
    resp = await client.get(
        f"/api/v1/internal/users/{user.id}/memories",
        params={"query": "where am I from"},
        headers={"X-Internal-Token": internal_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["memories"][0]["content"] == "User is from Russia"
    assert body["memories"][0]["similarity"] == 0.83


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
