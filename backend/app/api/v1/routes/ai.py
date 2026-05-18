"""AI chat endpoint."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.ai import ChatRequest, ChatResponse
from app.core.dependencies import get_current_user
from app.db import get_db_session
from app.db.models.user import User
from app.services.ai_agent import get_ai_agent_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Send a message to the AI agent. Requires authentication."""
    agent = get_ai_agent_service()
    try:
        response_text, conversation_id, trace_id = await agent.chat(
            message=body.message,
            user_id=current_user.id,
            conversation_id=body.conversation_id,
            db=db,
            background_tasks=background_tasks,
        )
        return ChatResponse(
            response=response_text,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
    except ValueError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not configured.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service encountered an error. Please try again.",
        ) from e
