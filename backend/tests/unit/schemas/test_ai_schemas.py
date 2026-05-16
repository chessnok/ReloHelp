"""Unit tests for app/api/v1/schemas/ai.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.ai import ChatRequest, ChatResponse


def test_chat_request_min_length():
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_request_max_length():
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 32_769)


def test_chat_request_optional_conversation_id():
    r = ChatRequest(message="hi")
    assert r.conversation_id is None


def test_chat_response_round_trip():
    r = ChatResponse(response="hi", conversation_id="cid", trace_id=None)
    assert r.response == "hi" and r.conversation_id == "cid"
