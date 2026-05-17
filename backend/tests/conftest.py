"""Pytest fixtures: patch Postgres-only column types to sqlite-compatible
types BEFORE importing any app modules, then provide async DB + httpx client."""

from __future__ import annotations

import os
import sys
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("DB_HOST", "test")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CSRF_SECRET_KEY", "test-csrf-secret")
os.environ.setdefault("COOKIE_DOMAIN", "")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("EMAIL_PROVIDER", "smtp")
os.environ.setdefault("DEBUG", "false")

import sqlalchemy as _sa
from sqlalchemy import CHAR, JSON
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.types import TypeDecorator

# Ensure aware UTC datetimes survive the sqlite roundtrip.
_orig_datetime = _DateTime


def _patched_datetime(*a, timezone: bool = False, **kw):
    inst = _orig_datetime(timezone=timezone, **kw)
    if not timezone:
        return inst
    return _TZAware()


class _TZAware(TypeDecorator):
    impl = _orig_datetime
    cache_ok = True

    def __init__(self, **kw):
        super().__init__(timezone=True, **kw)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        from datetime import timezone as _tz

        if value.tzinfo is None:
            return value.replace(tzinfo=_tz.utc)
        return value.astimezone(_tz.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        from datetime import timezone as _tz

        if value.tzinfo is None:
            return value.replace(tzinfo=_tz.utc)
        return value


_sa.DateTime = _patched_datetime


class _GUID(TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    def __init__(self, as_uuid: bool = False, **kw):
        super().__init__(**kw)
        self.as_uuid = as_uuid

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return str(value)
        return str(_uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _uuid.UUID(value) if not isinstance(value, _uuid.UUID) else value


class _JSONList(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, item_type=None, **kw):
        super().__init__(**kw)
        self.item_type = item_type

    def process_bind_param(self, value, dialect):
        return list(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return list(value) if value is not None else []


import sqlalchemy.dialects.postgresql as _pg
import sqlalchemy.dialects.postgresql.base as _pg_base

_pg.UUID = _GUID
_pg_base.UUID = _GUID
_sa.ARRAY = _JSONList

from typing import AsyncIterator

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cache.redis import RedisCache, get_redis_client
from app.db import base as db_base
from app.db.models import (
    Conversation,
    EmailVerificationToken,
    PasswordResetToken,
)
from app.db.models import (  # noqa: F401  (register tables on Base)
    Session as SessionModel,
)
from app.db.models import (
    User,
)
from app.db.session import get_db_session


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma_on_connect(dbapi_connection, _conn_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(db_base.Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_sessionmaker(db_engine):
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@pytest_asyncio.fixture
async def db_session(db_sessionmaker) -> AsyncIterator[AsyncSession]:
    async with db_sessionmaker() as session:
        yield session


@pytest.fixture
def fake_redis() -> RedisCache:
    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    return cache


@pytest_asyncio.fixture
async def app_instance(db_sessionmaker, fake_redis, monkeypatch):
    """FastAPI app with overridden DB + Redis dependencies + stubbed lifespan."""
    # Stub engine.connect() used by lifespan so it does not hit Postgres.
    from app.db import session as session_mod

    class _NoopConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **kw):
            class _R:
                def scalar(self_inner):
                    return None

            return _R()

    class _NoopEngine:
        def connect(self):
            return _NoopConn()

        async def dispose(self):
            return None

    monkeypatch.setattr(session_mod, "engine", _NoopEngine())

    from app.main import app

    async def _get_db_override():
        async with db_sessionmaker() as session:
            yield session

    async def _get_redis_override():
        return fake_redis

    app.dependency_overrides[get_db_session] = _get_db_override
    app.dependency_overrides[get_redis_client] = _get_redis_override
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def make_user(db_session):
    from app.core.security import hash_password

    async def _make(
        email: str = "user@example.com",
        password: str = "Password123",
        is_active: str = "active",
        email_is_verified: bool = True,
        roles: list[str] | None = None,
    ) -> User:
        user = User(
            id=_uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            is_active=is_active,
            email_is_verified=email_is_verified,
            roles=roles or [],
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make


@pytest_asyncio.fixture
async def make_session_record(db_session):
    from app.core.security import (
        create_refresh_token,
        generate_refresh_token_value,
        hash_refresh_token,
    )

    async def _make(user: User, expires_in_days: int = 30, revoked: bool = False):
        session_id = _uuid.uuid4()
        random_part = generate_refresh_token_value()
        refresh_value = create_refresh_token(session_id, random_part)
        record = SessionModel(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(random_part),
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            revoked_at=datetime.now(timezone.utc) if revoked else None,
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)
        return record, refresh_value, random_part

    return _make


@pytest.fixture
def access_token_for():
    from app.core.security import create_access_token

    def _build(user: User, jti: _uuid.UUID | None = None) -> str:
        return create_access_token(
            user_id=user.id,
            email=user.email,
            roles=user.roles or [],
            jti=jti or _uuid.uuid4(),
        )

    return _build
