"""Unit tests for MessageService against sqlite (via conftest fixtures)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.db.models.message import Message
from app.services.messages import MessageService, _to_openai_dict


async def test_ensure_conversation_creates_when_missing(db_session, make_user):
    user = await make_user()
    svc = MessageService()
    conv_id = uuid.uuid4()
    conv = await svc.ensure_conversation(db_session, conv_id, user.id)
    assert conv.id == conv_id
    assert conv.user_id == user.id
    await db_session.commit()


async def test_ensure_conversation_idempotent(db_session, make_user):
    user = await make_user()
    svc = MessageService()
    conv_id = uuid.uuid4()
    first = await svc.ensure_conversation(db_session, conv_id, user.id)
    await db_session.commit()
    second = await svc.ensure_conversation(db_session, conv_id, user.id)
    assert first.id == second.id


async def _insert(db_session, conv_id, role, content, ts, **kw):
    """Insert a Message with an explicit created_at so ordering is stable on
    sqlite (which lacks microsecond resolution on `now()`)."""
    m = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role=role,
        content=content,
        created_at=ts,
        **kw,
    )
    db_session.add(m)
    await db_session.flush()
    return m


async def test_append_and_load_history_round_trip(db_session, make_user):
    user = await make_user()
    svc = MessageService()
    conv_id = uuid.uuid4()
    await svc.ensure_conversation(db_session, conv_id, user.id)
    base = datetime.now(timezone.utc)
    await _insert(db_session, conv_id, "user", "first", base)
    await _insert(
        db_session,
        conv_id,
        "assistant",
        None,
        base + timedelta(seconds=1),
        tool_calls=[
            {
                "id": "t1",
                "type": "function",
                "function": {"name": "find_official_info", "arguments": "{}"},
            }
        ],
    )
    await _insert(
        db_session,
        conv_id,
        "tool",
        '{"ok":true}',
        base + timedelta(seconds=2),
        tool_call_id="t1",
    )
    await _insert(
        db_session, conv_id, "assistant", "final answer", base + timedelta(seconds=3)
    )
    await db_session.commit()

    history = await svc.load_history(db_session, conv_id, limit=20)
    assert [m["role"] for m in history] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert history[0]["content"] == "first"
    assert history[1].get("tool_calls") and not history[1]["content"]
    assert history[2]["tool_call_id"] == "t1"
    assert history[3]["content"] == "final answer"


async def test_load_history_respects_limit(db_session, make_user):
    user = await make_user()
    svc = MessageService()
    conv_id = uuid.uuid4()
    await svc.ensure_conversation(db_session, conv_id, user.id)
    base = datetime.now(timezone.utc)
    for i in range(5):
        await _insert(db_session, conv_id, "user", f"m{i}", base + timedelta(seconds=i))
    await db_session.commit()

    last_three = await svc.load_history(db_session, conv_id, limit=3)
    assert [m["content"] for m in last_three] == ["m2", "m3", "m4"]


async def test_append_method_persists(db_session, make_user):
    """Smoke-test the production `append()` path."""
    user = await make_user()
    svc = MessageService()
    conv_id = uuid.uuid4()
    await svc.ensure_conversation(db_session, conv_id, user.id)
    msg = await svc.append(db_session, conv_id, "user", "hello")
    await db_session.commit()
    assert msg.id
    history = await svc.load_history(db_session, conv_id, limit=10)
    assert len(history) == 1
    assert history[0]["content"] == "hello"


def test_to_openai_dict_skips_falsy_optional_fields():
    m = Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="ok",
        tool_calls=None,
        tool_call_id=None,
    )
    out = _to_openai_dict(m)
    assert "tool_calls" not in out
    assert "tool_call_id" not in out
    assert out["role"] == "assistant"
    assert out["content"] == "ok"
