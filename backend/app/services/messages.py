"""Persistence for chat conversation history."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation
from app.db.models.message import Message


class MessageService:
    """CRUD over the `messages` and `conversations` tables."""

    async def ensure_conversation(
        self, db: AsyncSession, conversation_id: UUID, user_id: UUID
    ) -> Conversation:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(id=conversation_id, user_id=user_id)
            db.add(conv)
            await db.flush()
        return conv

    async def append(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        role: str,
        content: str | None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> Message:
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        db.add(msg)
        await db.flush()
        return msg

    async def load_history(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return last `limit` messages oldest-first as OpenAI-formatted dicts.

        Sanitizes tool_call boundaries so the slice cannot start with an orphan
        `tool` message or end with an assistant `tool_calls` group whose tool
        responses got truncated — OpenAI rejects both shapes with HTTP 400.
        """
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        history = [_to_openai_dict(r) for r in rows]
        return _sanitize_tool_groups(history)


def _sanitize_tool_groups(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop orphan `tool` messages and incomplete assistant tool_calls groups.

    A truncated LIMIT slice can produce two shapes that OpenAI rejects:
      - `tool` message whose `tool_call_id` has no matching preceding
        assistant `tool_calls` entry within the slice.
      - assistant `tool_calls` whose tool responses got cut off.
    """
    out: list[dict[str, Any]] = []
    i = 0
    n = len(history)
    while i < n:
        m = history[i]
        role = m.get("role")
        if role == "tool":
            i += 1
            continue
        if role == "assistant" and m.get("tool_calls"):
            tc_ids = {tc["id"] for tc in m["tool_calls"] if tc.get("id")}
            j = i + 1
            tool_msgs: list[dict[str, Any]] = []
            seen: set[str] = set()
            while j < n and history[j].get("role") == "tool":
                tid = history[j].get("tool_call_id")
                if tid and tid in tc_ids and tid not in seen:
                    tool_msgs.append(history[j])
                    seen.add(tid)
                j += 1
            if seen == tc_ids and tc_ids:
                out.append(m)
                out.extend(tool_msgs)
            elif m.get("content"):
                out.append({"role": "assistant", "content": m["content"]})
            i = j
            continue
        out.append(m)
        i += 1
    return out


def _to_openai_dict(msg: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        out["tool_calls"] = msg.tool_calls
    if msg.tool_call_id:
        out["tool_call_id"] = msg.tool_call_id
    return out


_service: MessageService | None = None


def get_message_service() -> MessageService:
    global _service
    if _service is None:
        _service = MessageService()
    return _service
