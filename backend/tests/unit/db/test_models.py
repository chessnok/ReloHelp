"""Unit tests for app/db/models — ORM persistence + relationships."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    Conversation,
    EmailVerificationToken,
    PasswordResetToken,
)
from app.db.models import Session as SessionModel
from app.db.models import (
    User,
)


async def test_user_persists_with_defaults(db_session, make_user):
    u = await make_user(email="z@x.com")
    result = await db_session.execute(select(User).where(User.id == u.id))
    fetched = result.scalar_one()
    assert fetched.email == "z@x.com"
    assert fetched.is_active == "active"
    assert fetched.roles == []
    assert fetched.created_at is not None


async def test_user_has_relationships(db_session, make_user, make_session_record):
    user = await make_user()
    await make_session_record(user)
    await db_session.refresh(user, attribute_names=["sessions"])
    assert len(user.sessions) == 1


async def test_email_verification_token_relationship(db_session, make_user):
    u = await make_user()
    tok = EmailVerificationToken(
        id=uuid4(),
        user_id=u.id,
        token="v-tok",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(tok)
    await db_session.commit()
    await db_session.refresh(tok)
    assert tok.user.id == u.id


async def test_password_reset_token_relationship(db_session, make_user):
    u = await make_user()
    tok = PasswordResetToken(
        id=uuid4(),
        user_id=u.id,
        token="p-tok",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(tok)
    await db_session.commit()
    await db_session.refresh(tok)
    assert tok.user.id == u.id


async def test_session_revoked_at_round_trip(db_session, make_user):
    u = await make_user()
    sid = uuid4()
    rec = SessionModel(
        id=sid,
        user_id=u.id,
        refresh_token_hash="hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add(rec)
    await db_session.commit()
    fetched = (
        await db_session.execute(select(SessionModel).where(SessionModel.id == sid))
    ).scalar_one()
    assert fetched.revoked_at is not None


async def test_conversation_back_to_user(db_session, make_user):
    u = await make_user()
    conv = Conversation(id=uuid4(), user_id=u.id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.user.id == u.id


async def test_cascade_delete_user_removes_sessions(
    db_session, make_user, make_session_record
):
    u = await make_user()
    rec, _, _ = await make_session_record(u)
    await db_session.delete(u)
    await db_session.commit()
    remaining = (
        await db_session.execute(select(SessionModel).where(SessionModel.id == rec.id))
    ).scalar_one_or_none()
    assert remaining is None
