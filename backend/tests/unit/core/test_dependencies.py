"""Unit tests for app/core/dependencies.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.core import dependencies as deps


async def test_get_current_user_no_token_raises_401(db_session):
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(access_token=None, db=db_session)
    assert exc.value.status_code == 401


async def test_get_current_user_invalid_token_raises_401(db_session):
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(access_token="bad", db=db_session)
    assert exc.value.status_code == 401


async def test_get_current_user_wrong_type_raises_401(db_session, make_user):
    import jwt

    from app.core.config import settings as cfg

    user = await make_user()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "jti": str(uuid4()),
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        cfg.JWT_SECRET_KEY,
        algorithm=cfg.JWT_ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(access_token=token, db=db_session)
    assert exc.value.status_code == 401


async def test_get_current_user_returns_user(db_session, make_user, access_token_for):
    user = await make_user(email="ok@x.com")
    token = access_token_for(user)
    got = await deps.get_current_user(access_token=token, db=db_session)
    assert got.id == user.id


async def test_get_current_user_missing_user_raises_401(db_session, access_token_for):
    class _Fake:
        id = uuid4()
        email = "ghost@x.com"
        roles = []

    token = access_token_for(_Fake())
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(access_token=token, db=db_session)
    assert exc.value.status_code == 401


async def test_get_current_user_inactive_raises_403(
    db_session, make_user, access_token_for
):
    # Falsy is_active triggers the inactive branch in dependencies.get_current_user.
    user = await make_user(email="off@x.com", is_active="")
    token = access_token_for(user)
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(access_token=token, db=db_session)
    assert exc.value.status_code == 403


async def test_get_refresh_session_no_token_raises(db_session):
    with pytest.raises(HTTPException) as exc:
        await deps.get_refresh_session(refresh_token=None, db=db_session)
    assert exc.value.status_code == 401


async def test_get_refresh_session_ok(db_session, make_user, make_session_record):
    user = await make_user()
    rec, refresh_value, _ = await make_session_record(user)
    session, _rnd = await deps.get_refresh_session(
        refresh_token=refresh_value, db=db_session
    )
    assert session.id == rec.id


async def test_get_refresh_session_revoked_raises(
    db_session, make_user, make_session_record
):
    user = await make_user()
    _, refresh_value, _ = await make_session_record(user, revoked=True)
    with pytest.raises(HTTPException) as exc:
        await deps.get_refresh_session(refresh_token=refresh_value, db=db_session)
    assert exc.value.status_code == 401


def test_get_csrf_token_reads_header():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-csrf-token", b"abc")],
    }
    assert deps.get_csrf_token(Request(scope)) == "abc"
