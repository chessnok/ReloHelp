"""Integration tests for /auth routes via httpx ASGI client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.email import email_service
from app.db.models import EmailVerificationToken, PasswordResetToken, Session, User


@pytest.fixture(autouse=True)
def _no_real_emails(monkeypatch):
    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(email_service, "send_verification_email", _noop)
    monkeypatch.setattr(email_service, "send_password_reset_email", _noop)


class TestRegister:
    async def test_creates_user_and_token(self, client, db_session):
        resp = await client.post(
            "/auth/register",
            json={"email": "new@x.com", "password": "Password1"},
        )
        assert resp.status_code == 201
        users = (await db_session.execute(select(User))).scalars().all()
        assert any(u.email == "new@x.com" for u in users)
        tokens = (
            (await db_session.execute(select(EmailVerificationToken))).scalars().all()
        )
        assert len(tokens) == 1

    async def test_duplicate_email_rejected(self, client, make_user):
        await make_user(email="dup@x.com")
        resp = await client.post(
            "/auth/register",
            json={"email": "dup@x.com", "password": "Password1"},
        )
        assert resp.status_code == 400

    async def test_weak_password_rejected(self, client):
        resp = await client.post(
            "/auth/register",
            json={"email": "weak@x.com", "password": "weakpass"},
        )
        assert resp.status_code == 422


class TestLogin:
    async def test_success_sets_cookies(self, client, make_user):
        await make_user(email="login@x.com", password="Password1")
        resp = await client.post(
            "/auth/login",
            json={"email": "login@x.com", "password": "Password1"},
        )
        assert resp.status_code == 200
        cookie_names = {c.split("=", 1)[0] for c in resp.headers.get_list("set-cookie")}
        assert {"access_token", "refresh_token", "csrf_token"} <= cookie_names

    async def test_wrong_password_returns_401(self, client, make_user):
        await make_user(email="x@x.com", password="Password1")
        resp = await client.post(
            "/auth/login",
            json={"email": "x@x.com", "password": "BadPass1"},
        )
        assert resp.status_code == 401

    async def test_inactive_user_returns_403(self, client, make_user):
        await make_user(email="off@x.com", password="Password1", is_active="off")
        resp = await client.post(
            "/auth/login",
            json={"email": "off@x.com", "password": "Password1"},
        )
        assert resp.status_code == 403


class TestVerifyEmail:
    async def test_valid_token_marks_verified(self, client, db_session, make_user):
        u = await make_user(email_is_verified=False)
        token = EmailVerificationToken(
            id=uuid4(),
            user_id=u.id,
            token="vtok",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(token)
        await db_session.commit()
        resp = await client.post("/auth/verify-email", json={"token": "vtok"})
        assert resp.status_code == 200
        await db_session.refresh(u)
        assert u.email_is_verified is True

    async def test_unknown_token_rejected(self, client):
        resp = await client.post("/auth/verify-email", json={"token": "no"})
        assert resp.status_code == 400

    async def test_expired_token_rejected(self, client, db_session, make_user):
        u = await make_user()
        token = EmailVerificationToken(
            id=uuid4(),
            user_id=u.id,
            token="exp",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(token)
        await db_session.commit()
        resp = await client.post("/auth/verify-email", json={"token": "exp"})
        assert resp.status_code == 400


class TestMe:
    async def test_returns_user(self, client, make_user, access_token_for):
        u = await make_user(email="me@x.com")
        token = access_token_for(u)
        client.cookies.set("access_token", token)
        resp = await client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@x.com"

    async def test_no_cookie_returns_401(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


class TestSessions:
    async def test_list_returns_active_sessions(
        self, client, make_user, access_token_for, make_session_record
    ):
        u = await make_user()
        await make_session_record(u)
        client.cookies.set("access_token", access_token_for(u))
        resp = await client.get("/auth/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_delete_session(
        self, client, db_session, make_user, access_token_for, make_session_record
    ):
        u = await make_user()
        rec, _, _ = await make_session_record(u)
        client.cookies.set("access_token", access_token_for(u))
        resp = await client.delete(f"/auth/sessions/{rec.id}")
        assert resp.status_code == 204
        await db_session.refresh(rec)
        assert rec.revoked_at is not None

    async def test_delete_missing_session_404(
        self, client, make_user, access_token_for
    ):
        u = await make_user()
        client.cookies.set("access_token", access_token_for(u))
        resp = await client.delete(f"/auth/sessions/{uuid4()}")
        assert resp.status_code == 404


class TestRefreshAndLogout:
    async def test_refresh_rotates_session(
        self, client, db_session, make_user, make_session_record
    ):
        u = await make_user()
        rec, refresh_value, _ = await make_session_record(u)
        client.cookies.set("refresh_token", refresh_value)
        resp = await client.post("/auth/token/refresh")
        assert resp.status_code == 200, resp.text
        await db_session.refresh(rec)
        assert rec.revoked_at is not None
        sessions = (await db_session.execute(select(Session))).scalars().all()
        assert len(sessions) == 2

    async def test_logout_revokes_session(
        self, client, db_session, make_user, make_session_record
    ):
        u = await make_user()
        rec, refresh_value, _ = await make_session_record(u)
        client.cookies.set("refresh_token", refresh_value)
        resp = await client.post("/auth/logout")
        assert resp.status_code == 204
        await db_session.refresh(rec)
        assert rec.revoked_at is not None


class TestPasswordReset:
    async def test_forgot_password_creates_token(self, client, db_session, make_user):
        await make_user(email="pw@x.com")
        resp = await client.post("/auth/password/forgot", json={"email": "pw@x.com"})
        assert resp.status_code == 200
        tokens = (await db_session.execute(select(PasswordResetToken))).scalars().all()
        assert len(tokens) == 1

    async def test_forgot_password_unknown_email_returns_ok(self, client):
        resp = await client.post("/auth/password/forgot", json={"email": "no@x.com"})
        assert resp.status_code == 200

    async def test_reset_password_success_revokes_sessions(
        self,
        client,
        db_session,
        make_user,
        make_session_record,
    ):
        u = await make_user(email="r@x.com", password="OldPass1")
        rec, _, _ = await make_session_record(u)
        tok = PasswordResetToken(
            id=uuid4(),
            user_id=u.id,
            token="rtok",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(tok)
        await db_session.commit()

        resp = await client.post(
            "/auth/password/reset",
            json={"token": "rtok", "new_password": "NewPass1"},
        )
        assert resp.status_code == 200
        await db_session.refresh(rec)
        assert rec.revoked_at is not None

    async def test_reset_password_invalid_token(self, client):
        resp = await client.post(
            "/auth/password/reset",
            json={"token": "nope", "new_password": "NewPass1"},
        )
        assert resp.status_code == 400

    async def test_reset_password_expired_token(self, client, db_session, make_user):
        u = await make_user()
        tok = PasswordResetToken(
            id=uuid4(),
            user_id=u.id,
            token="rtoke",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(tok)
        await db_session.commit()
        resp = await client.post(
            "/auth/password/reset",
            json={"token": "rtoke", "new_password": "NewPass1"},
        )
        assert resp.status_code == 400


class TestResendVerification:
    async def test_unknown_email_returns_generic_ok(self, client):
        resp = await client.post("/auth/verify-email/resend", json={"email": "x@x.com"})
        assert resp.status_code == 200

    async def test_already_verified_returns_generic_ok(self, client, make_user):
        await make_user(email="v@x.com", email_is_verified=True)
        resp = await client.post("/auth/verify-email/resend", json={"email": "v@x.com"})
        assert resp.status_code == 200
