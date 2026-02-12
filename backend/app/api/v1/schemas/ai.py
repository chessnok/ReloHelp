"""Pydantic schemas for AI chat API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/ai/chat."""

    message: str = Field(..., min_length=1, max_length=32_768)
    conversation_id: str | None = Field(None, description="Optional conversation ID for multi-turn context.")


class ChatResponse(BaseModel):
    """Response body for POST /api/ai/chat."""

    response: str
    conversation_id: str
    trace_id: str | None = None
